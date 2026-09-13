#!/usr/bin/env python3
"""Baseline CONTROL: stock torchvision detectors on the phase-2 rice/weed task.

`docs/GATE_STATUS.md` blocks any headline accuracy claim on one thing: there is
nothing to measure WeedDet against. An AP of 0.31 is neither good nor bad until a
maintained reference detector has been run on the *same* images, at the *same*
resolution, through the *same* evaluator. This module is that reference.

Comparability is the whole point, so the arms are held identical by construction
rather than by convention:

* **Same pixels.** The dataset is ``_CocoSplitDataset`` -- the exact class the
  WeedDet trainer uses. Same letterbox, same per-axis scales, same label-aligned
  augmentation, same ImageNet normalisation, same class map.
* **Same input tensor.** torchvision detectors normally resize and normalise
  internally. Both are disabled here (``image_mean=0``, ``image_std=1``,
  ``min_size == max_size == img_size``), so the reference model receives byte-for-byte
  the tensor WeedDet receives. 512 is divisible by 32, so the batching pad is a
  no-op too.
* **Same scoring path.** Predictions go through the same
  :func:`~agrinav.inference.postprocess.invert_letterbox` and
  :func:`~agrinav.inference.postprocess.to_coco_detections` as the WeedDet arm and
  are scored by the same ``pycocotools`` call at the same ``maxDets``.

One residual difference is unavoidable and is recorded in every report rather
than papered over: **torchvision applies its own hard NMS inside the model**,
while the WeedDet arm defaults to Soft-NMS. Score threshold, NMS IoU and
detections-per-image are matched to the WeedDet defaults, but for a strict
head-to-head run the WeedDet arm with ``--hard-nms``. ``protocol.suppression``
says which was used, so the two can never be silently mixed.

The label convention differs too, and is converted at both ends: torchvision
reserves class 0 for background, so targets are emitted as ``idx + 1`` and
predictions are mapped back with ``label - 1`` before the COCO category lookup.

    agrinav baseline-detector \\
        --arch fasterrcnn_resnet50_fpn_v2 \\
        --ann-file      <data>/annotations/instances_train.coco.json \\
        --images-root   <data>/images/train \\
        --val-ann-file  <data>/annotations/instances_valid.coco.json \\
        --val-images-root <data>/images/valid \\
        --config configs/training/baseline_det_control.yaml \\
        --out-dir runs/baseline_frcnn

A ``--self-test`` mode builds a tiny synthetic split and runs one epoch on CPU,
so the plumbing is verifiable without the dataset or a GPU.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import torch

from agrinav.evaluation.metrics import evaluate_coco_detections
from agrinav.inference.postprocess import (
    DEFAULT_MAX_DETECTIONS,
    DEFAULT_NMS_IOU,
    DEFAULT_SCORE_THRESHOLD,
    invert_letterbox,
    to_coco_detections,
)

SCHEMA_VERSION = "agrinav.baseline_det_control.run.v1"

#: Reference architectures. Each is a maintained torchvision detector with a
#: published COCO number, so a reader can sanity-check that our training recipe
#: is not the thing holding the baseline down.
SUPPORTED_ARCHS: tuple[str, ...] = (
    "fasterrcnn_resnet50_fpn_v2",  # two-stage reference
    "retinanet_resnet50_fpn_v2",  # one-stage dense reference (WeedDet's family)
    "fcos_resnet50_fpn",  # one-stage anchor-free reference
)

#: torchvision reserves label 0 for background in all three heads, so the
#: classification head is built with one extra output and our contiguous class
#: indices are shifted into [1, N].
BACKGROUND_LABEL = 0

DEFAULT_IMG_SIZE = 512
DEFAULT_EVAL_BATCH_SIZE = 8


class BaselineError(RuntimeError):
    """Raised when a baseline run cannot be configured or executed correctly."""


# ==================================================================== configuration
@dataclass
class BaselineConfig:
    """Everything that decides what a baseline run *is*.

    Defaults mirror ``configs/training/detector_rice_phase2.yaml`` wherever the
    two recipes can agree, because a baseline trained on a different budget is a
    different experiment. Where they cannot agree -- optimiser, LR -- the
    torchvision reference recipe is used and the difference is recorded.
    """

    arch: str = "fasterrcnn_resnet50_fpn_v2"
    init: str = "coco"  # coco | imagenet | scratch
    class_names: tuple[str, ...] = ("rice_protect", "weed_target")
    img_size: int = DEFAULT_IMG_SIZE
    batch_size: int = 4  # two-stage detectors need more memory than WeedDet
    num_workers: int = 2
    num_epochs: int = 18
    base_lr: float = 0.005  # torchvision reference SGD recipe, scaled for batch 4
    momentum: float = 0.9
    weight_decay: float = 0.0001
    warmup_iters: int = 500
    min_lr: float = 0.00001
    grad_clip: float = 0.5
    augment: bool = True
    use_amp: bool = True
    seed: int = 42
    deterministic: bool = False
    trainable_backbone_layers: int = 3
    # --- evaluation protocol, matched to the WeedDet arm ---
    score_threshold: float = DEFAULT_SCORE_THRESHOLD
    nms_iou: float = DEFAULT_NMS_IOU
    max_detections: int = DEFAULT_MAX_DETECTIONS
    eval_batch_size: int = DEFAULT_EVAL_BATCH_SIZE
    val_ap_interval: int = 2

    def validate(self) -> None:
        """Reject a configuration that would produce an uninterpretable number.

        Raises:
            BaselineError: on an unknown architecture or init, an empty class
                list, or a non-positive size/budget.
        """
        if self.arch not in SUPPORTED_ARCHS:
            raise BaselineError(
                f"unknown --arch {self.arch!r}. Supported: {', '.join(SUPPORTED_ARCHS)}"
            )
        if self.init not in ("coco", "imagenet", "scratch"):
            raise BaselineError(
                f"unknown --init {self.init!r}; expected one of coco, imagenet, scratch"
            )
        if not self.class_names:
            raise BaselineError("class_names is empty; the class map decides the whole task")
        for name, value in (
            ("img_size", self.img_size),
            ("batch_size", self.batch_size),
            ("num_epochs", self.num_epochs),
            ("max_detections", self.max_detections),
        ):
            if value <= 0:
                raise BaselineError(f"{name} must be positive, got {value!r}")
        if self.img_size % 32:
            raise BaselineError(
                f"img_size={self.img_size} is not a multiple of 32. torchvision pads the batch "
                "up to a multiple of 32, which would make the reference model see a larger "
                "canvas than WeedDet and quietly break comparability."
            )

    @property
    def num_torchvision_classes(self) -> int:
        """Foreground classes plus torchvision's background slot at index 0."""
        return len(self.class_names) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "arch": self.arch,
            "init": self.init,
            "class_names": list(self.class_names),
            "img_size": self.img_size,
            "batch_size": self.batch_size,
            "num_workers": self.num_workers,
            "num_epochs": self.num_epochs,
            "base_lr": self.base_lr,
            "momentum": self.momentum,
            "weight_decay": self.weight_decay,
            "warmup_iters": self.warmup_iters,
            "min_lr": self.min_lr,
            "grad_clip": self.grad_clip,
            "augment": self.augment,
            "use_amp": self.use_amp,
            "seed": self.seed,
            "deterministic": self.deterministic,
            "trainable_backbone_layers": self.trainable_backbone_layers,
            "score_threshold": self.score_threshold,
            "nms_iou": self.nms_iou,
            "max_detections": self.max_detections,
            "eval_batch_size": self.eval_batch_size,
            "val_ap_interval": self.val_ap_interval,
        }


@dataclass
class EpochRecord:
    """One row of the training log."""

    epoch: int
    train_loss: float
    loss_components: dict[str, float] = field(default_factory=dict)
    val_ap: float | None = None
    lr: float = 0.0
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "train_loss": self.train_loss,
            "loss_components": self.loss_components,
            "val_ap": self.val_ap,
            "lr": self.lr,
            "seconds": round(self.seconds, 2),
        }


# ======================================================================= model build
def build_model(config: BaselineConfig) -> Any:
    """Construct a torchvision detector wired for this task and this protocol.

    Three things are changed from the stock constructor, each for a stated reason:
    the classification head is rebuilt for our class count; the internal
    resize/normalise transform is neutralised so the model sees WeedDet's exact
    tensor; and the score/NMS/detection-cap knobs are set to the WeedDet defaults.

    Args:
        config: validated run configuration.

    Returns:
        A torchvision detection model in train mode.

    Raises:
        BaselineError: if the architecture is unsupported.
    """
    import torchvision
    from torchvision.models.detection import faster_rcnn, fcos, retinanet

    num_classes = config.num_torchvision_classes
    weights = None
    weights_backbone = None
    if config.init == "coco":
        weights = "DEFAULT"
    elif config.init == "imagenet":
        weights_backbone = "DEFAULT"

    common: dict[str, Any] = {
        "weights": weights,
        "weights_backbone": weights_backbone,
        # Neutralise the internal transform: no resize (min == max == our size),
        # no second normalisation (the dataset already applied ImageNet stats).
        "min_size": config.img_size,
        "max_size": config.img_size,
        "image_mean": [0.0, 0.0, 0.0],
        "image_std": [1.0, 1.0, 1.0],
    }
    # torchvision warns and silently overrides this when nothing is pretrained --
    # there is no such thing as freezing layers of a randomly initialised backbone.
    if weights or weights_backbone:
        common["trainable_backbone_layers"] = config.trainable_backbone_layers

    if config.arch == "fasterrcnn_resnet50_fpn_v2":
        model = torchvision.models.detection.fasterrcnn_resnet50_fpn_v2(
            box_score_thresh=config.score_threshold,
            box_nms_thresh=config.nms_iou,
            box_detections_per_img=config.max_detections,
            **common,
        )
        in_features = model.roi_heads.box_predictor.cls_score.in_features
        model.roi_heads.box_predictor = faster_rcnn.FastRCNNPredictor(in_features, num_classes)
    elif config.arch == "retinanet_resnet50_fpn_v2":
        model = torchvision.models.detection.retinanet_resnet50_fpn_v2(
            score_thresh=config.score_threshold,
            nms_thresh=config.nms_iou,
            detections_per_img=config.max_detections,
            **common,
        )
        head = model.head.classification_head
        # Read the shape off `cls_logits` rather than walking `conv`: the v2 head
        # wraps its convs in Conv2dNormActivation blocks and FCOS does not, so
        # indexing into `conv` is a structure assumption that breaks per-arch.
        model.head.classification_head = retinanet.RetinaNetClassificationHead(
            in_channels=head.cls_logits.in_channels,
            num_anchors=head.num_anchors,
            num_classes=num_classes,
            norm_layer=lambda channels: torch.nn.GroupNorm(32, channels),
        )
    elif config.arch == "fcos_resnet50_fpn":
        model = torchvision.models.detection.fcos_resnet50_fpn(
            score_thresh=config.score_threshold,
            nms_thresh=config.nms_iou,
            detections_per_img=config.max_detections,
            **common,
        )
        head = model.head.classification_head
        model.head.classification_head = fcos.FCOSClassificationHead(
            in_channels=head.cls_logits.in_channels,
            num_anchors=head.num_anchors,
            num_classes=num_classes,
            norm_layer=lambda channels: torch.nn.GroupNorm(32, channels),
        )
    else:  # pragma: no cover - validate() rejects this first
        raise BaselineError(f"unsupported arch {config.arch!r}")

    return model


def to_torchvision_targets(
    targets: Sequence[Mapping[str, Any]], device: str = "cpu"
) -> list[dict[str, torch.Tensor]]:
    """Convert ``_CocoSplitDataset`` targets into torchvision's target dicts.

    The only substantive change is the label shift: our class indices are
    contiguous from 0, torchvision's background occupies 0, so foreground labels
    move into ``[1, N]``. Boxes are already xyxy in letterbox space, which is the
    space the model works in.

    Degenerate boxes are dropped here as well as in the dataset, because
    torchvision raises on a zero-area box and a hard crash mid-epoch is a worse
    failure than a silently missing box that the report can count.
    """
    converted: list[dict[str, torch.Tensor]] = []
    for target in targets:
        boxes = target["boxes"].to(device=device, dtype=torch.float32)
        labels = target["labels"].to(device=device, dtype=torch.int64) + 1
        if boxes.numel():
            keep = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
            boxes, labels = boxes[keep], labels[keep]
        converted.append({"boxes": boxes.reshape(-1, 4), "labels": labels.reshape(-1)})
    return converted


# ========================================================================= evaluation
def predict_split(
    model: Any,
    dataset: Any,
    config: BaselineConfig,
    *,
    device: str = "cpu",
    index_to_category_id: Mapping[int, int] | None = None,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Run the reference detector over a split and return COCO detection records.

    Mirrors :func:`agrinav.evaluation.runner.predict_split` step for step, with
    torchvision's forward pass and label convention substituted. Suppression has
    already happened inside the model, so this only inverts the letterbox and
    maps ids.

    Raises:
        BaselineError: if the dataset is empty or exposes no class map.
    """
    from PIL import Image

    import agrinav.models.weeddet_v6b as weeddet

    items = list(dataset.items())
    if not items:
        raise BaselineError("dataset exposes no items(); nothing to evaluate")

    if index_to_category_id is None:
        catid_to_idx = getattr(dataset, "catid_to_idx", None)
        if not catid_to_idx:
            raise BaselineError(
                "no class map available: pass index_to_category_id, or use a dataset "
                "exposing catid_to_idx"
            )
        index_to_category_id = {index: cid for cid, index in catid_to_idx.items()}

    transform = weeddet.T.Compose(
        [
            weeddet.T.ToTensor(),
            weeddet.T.Normalize(mean=weeddet.IMAGENET_MEAN, std=weeddet.IMAGENET_STD),
        ]
    )

    was_training = model.training
    model.eval().to(device)
    detections: list[dict[str, Any]] = []
    try:
        with torch.no_grad():
            for start in range(0, len(items), config.eval_batch_size):
                batch = items[start : start + config.eval_batch_size]
                tensors, geometry = [], []
                for _image_id, path, _width, _height in batch:
                    with Image.open(os.fspath(path)) as handle:
                        image = handle.convert("RGB")
                        original_size = image.size
                        letterboxed, scale_x, scale_y, pad_left, pad_top = weeddet.letterbox_pil(
                            image, config.img_size
                        )
                    tensors.append(transform(letterboxed).to(device))
                    geometry.append((scale_x, scale_y, pad_left, pad_top, original_size))

                outputs = model(tensors)

                for (image_id, _path, _w, _h), result, geom in zip(batch, outputs, geometry):
                    scale_x, scale_y, pad_left, pad_top, (orig_w, orig_h) = geom
                    boxes = result["boxes"].detach().cpu()
                    scores = result["scores"].detach().cpu()
                    # Shift back out of torchvision's background-at-0 convention.
                    labels = result["labels"].detach().cpu() - 1
                    if boxes.numel():
                        valid = labels >= 0
                        boxes, scores, labels = boxes[valid], scores[valid], labels[valid]
                    if boxes.numel():
                        boxes, inside = invert_letterbox(
                            boxes,
                            scale_x,
                            scale_y,
                            pad_left,
                            pad_top,
                            orig_w=orig_w,
                            orig_h=orig_h,
                        )
                        boxes, scores, labels = boxes[inside], scores[inside], labels[inside]
                    detections.extend(
                        to_coco_detections(boxes, scores, labels, image_id, index_to_category_id)
                    )

                if progress and (start // config.eval_batch_size) % 10 == 0:
                    print(
                        f"  [baseline-eval] {min(start + config.eval_batch_size, len(items))}/"
                        f"{len(items)} images, {len(detections)} detections",
                        flush=True,
                    )
    finally:
        if was_training:
            model.train()
    return detections


def evaluate_split(
    model: Any,
    dataset: Any,
    ann_file: str | os.PathLike[str],
    config: BaselineConfig,
    *,
    device: str = "cpu",
    progress: bool = False,
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    """Predict over a split and score it, returning ``(result, detections, protocol)``.

    ``protocol`` uses the same keys as the WeedDet evaluator's so two reports can
    be diffed directly, plus a ``suppression`` field naming the difference that
    cannot be removed.
    """
    started = time.time()
    detections = predict_split(model, dataset, config, device=device, progress=progress)
    predict_seconds = time.time() - started

    result = evaluate_coco_detections(
        os.fspath(ann_file), detections, max_dets=config.max_detections
    )
    protocol = {
        "img_size": config.img_size,
        "score_threshold": config.score_threshold,
        "nms_iou": config.nms_iou,
        "max_detections": config.max_detections,
        "use_soft_nms": False,
        "pre_nms_topk": None,
        "device": device,
        "is_standard_maxdets": result.is_standard_maxdets,
        "predict_seconds": round(predict_seconds, 2),
        "images": len(list(dataset.items())),
        "detections": len(detections),
        "postprocessor": f"torchvision {config.arch} built-in (hard NMS)",
        "suppression": (
            "torchvision applies hard NMS inside the model. The WeedDet arm defaults to "
            "Soft-NMS; run it with --hard-nms for a strict head-to-head."
        ),
    }
    return result, detections, protocol


# =========================================================================== training
def _set_seed(seed: int, deterministic: bool) -> None:
    """Seed Python, NumPy and torch. Determinism is opt-in and costs throughput."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # numpy is a hard dep in practice; do not fail the run on it
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    else:
        torch.backends.cudnn.benchmark = True


def _lr_at(step: int, total_steps: int, config: BaselineConfig) -> float:
    """Linear warmup into a cosine decay -- the same shape the WeedDet recipe uses."""
    if step < config.warmup_iters:
        alpha = (step + 1) / max(1, config.warmup_iters)
        return config.base_lr * alpha
    progress = (step - config.warmup_iters) / max(1, total_steps - config.warmup_iters)
    progress = min(1.0, max(0.0, progress))
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return config.min_lr + (config.base_lr - config.min_lr) * cosine


def train(
    config: BaselineConfig,
    train_dataset: Any,
    *,
    val_dataset: Any | None = None,
    val_ann_file: str | os.PathLike[str] | None = None,
    out_dir: str | os.PathLike[str],
    device: str = "cpu",
    model: Any | None = None,
) -> dict[str, Any]:
    """Train one reference detector and return its run record.

    Checkpoint selection is on validation AP when a validation split is supplied,
    for the same reason the WeedDet trainer selects on it: a detector can lower
    its loss while its detections get worse. Without a validation split the run
    is a plumbing check, not a baseline, and the record says so.

    Args:
        config: validated configuration.
        train_dataset: a ``_CocoSplitDataset``-shaped training split.
        val_dataset: optional validation split, scored every
            ``config.val_ap_interval`` epochs.
        val_ann_file: ground truth for ``val_dataset``. Required with it.
        out_dir: directory for checkpoints and the run record.
        device: torch device string.
        model: pre-built model, for tests. Built from ``config`` when omitted.

    Returns:
        The run record, also written to ``out_dir/run.json``.

    Raises:
        BaselineError: on an inconsistent validation configuration or a
            non-finite loss.
    """
    from torch.utils.data import DataLoader

    import agrinav.models.weeddet_v6b as weeddet

    config.validate()
    if (val_dataset is None) != (val_ann_file is None):
        raise BaselineError(
            "val_dataset and val_ann_file must be given together: AP needs both the "
            "images and the ground truth they are scored against."
        )

    out_dir = os.fspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    _set_seed(config.seed, config.deterministic)

    if model is None:
        model = build_model(config)
    model.to(device)

    loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        collate_fn=weeddet.collate_fn,
        drop_last=False,
    )
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(
        params, lr=config.base_lr, momentum=config.momentum, weight_decay=config.weight_decay
    )
    use_amp = config.use_amp and device.startswith("cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    total_steps = max(1, len(loader) * config.num_epochs)
    history: list[EpochRecord] = []
    best_ap = -1.0
    best_epoch: int | None = None
    step = 0
    started = time.time()

    for epoch in range(1, config.num_epochs + 1):
        model.train()
        epoch_started = time.time()
        running = 0.0
        components: dict[str, float] = {}
        batches = 0
        last_lr = config.base_lr

        for images, targets in loader:
            if not len(images):
                continue
            images = images.to(device)
            batch_targets = to_torchvision_targets(targets, device=device)

            last_lr = _lr_at(step, total_steps, config)
            for group in optimizer.param_groups:
                group["lr"] = last_lr

            with torch.amp.autocast("cuda", enabled=use_amp):
                loss_dict = model(list(images), batch_targets)
                loss = sum(loss_dict.values())

            if not torch.isfinite(loss):
                components_now = {k: float(v.detach()) for k, v in loss_dict.items()}
                raise BaselineError(
                    f"non-finite loss at epoch {epoch} step {step}: {components_now}. "
                    "Lower base_lr or disable AMP before reading anything into this run."
                )

            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            if config.grad_clip:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(params, config.grad_clip)
            scaler.step(optimizer)
            scaler.update()

            running += float(loss.detach())
            for name, value in loss_dict.items():
                components[name] = components.get(name, 0.0) + float(value.detach())
            batches += 1
            step += 1

        train_loss = running / max(1, batches)
        record = EpochRecord(
            epoch=epoch,
            train_loss=train_loss,
            loss_components={k: v / max(1, batches) for k, v in components.items()},
            lr=last_lr,
            seconds=time.time() - epoch_started,
        )

        should_eval = (
            val_dataset is not None
            and config.val_ap_interval > 0
            and (epoch % config.val_ap_interval == 0 or epoch == config.num_epochs)
        )
        if should_eval:
            assert val_ann_file is not None  # guarded above
            result, _detections, _protocol = evaluate_split(
                model, val_dataset, val_ann_file, config, device=device
            )
            record.val_ap = float(result.ap)
            if record.val_ap > best_ap:
                best_ap, best_epoch = record.val_ap, epoch
                _save(model, config, os.path.join(out_dir, "baseline_best.pth"), epoch, best_ap)

        history.append(record)
        _save(model, config, os.path.join(out_dir, "baseline_last.pth"), epoch, record.val_ap)
        print(
            f"epoch {epoch}/{config.num_epochs}  loss {train_loss:.4f}"
            + (f"  val/AP {record.val_ap:.4f}" if record.val_ap is not None else "")
            + f"  lr {last_lr:.2e}  {record.seconds:.1f}s",
            flush=True,
        )

    run = {
        "schema_version": SCHEMA_VERSION,
        "arch": config.arch,
        "config": config.to_dict(),
        "device": device,
        "train_images": len(train_dataset),
        "val_images": len(val_dataset) if val_dataset is not None else 0,
        "epochs": [r.to_dict() for r in history],
        "best_val_ap": best_ap if best_epoch is not None else None,
        "best_epoch": best_epoch,
        "selection_metric": "val/AP" if best_epoch is not None else "none (no validation split)",
        "total_seconds": round(time.time() - started, 2),
        "torch_version": torch.__version__,
    }
    if best_epoch is None:
        run["warning"] = (
            "No validation split was supplied, so no checkpoint was selected and this run "
            "is a plumbing check, not a baseline. Re-run with --val-ann-file/--val-images-root "
            "before comparing anything to it."
        )

    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as handle:
        json.dump(run, handle, indent=2, sort_keys=True)
    return run


def _save(model: Any, config: BaselineConfig, path: str, epoch: int, metric: float | None) -> None:
    """Write a checkpoint carrying enough metadata to be scored later without guessing."""
    torch.save(
        {
            "schema_version": SCHEMA_VERSION,
            "model": model.state_dict(),
            "arch": config.arch,
            "config": config.to_dict(),
            "class_names": list(config.class_names),
            "epoch": epoch,
            "metric": metric,
            "selection_metric": "val/AP",
        },
        path,
    )


# ============================================================================== CLI
def _load_yaml_config(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read a YAML config, failing loudly rather than falling back to defaults."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - PyYAML is a declared dependency
        raise BaselineError(
            "PyYAML is required to read --config. Install it, or pass every option on the CLI."
        ) from exc
    with open(os.fspath(path), encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise BaselineError(f"{path!r} must contain a YAML mapping, got {type(loaded).__name__}")
    return loaded


def build_config(args: argparse.Namespace) -> BaselineConfig:
    """Compose a config from defaults, then the YAML file, then explicit CLI flags."""
    values: dict[str, Any] = {}
    if args.config:
        loaded = _load_yaml_config(args.config)
        known = set(BaselineConfig().to_dict())
        unknown = sorted(set(loaded) - known)
        if unknown:
            raise BaselineError(
                f"{args.config!r} sets unknown keys {unknown}. A silently ignored key is how "
                "a run ends up not being the run its config describes."
            )
        values.update(loaded)

    for flag in (
        "arch",
        "init",
        "img_size",
        "batch_size",
        "num_workers",
        "num_epochs",
        "base_lr",
        "seed",
        "val_ap_interval",
        "score_threshold",
        "nms_iou",
        "max_detections",
    ):
        supplied = getattr(args, flag, None)
        if supplied is not None:
            values[flag] = supplied
    if args.class_names:
        values["class_names"] = tuple(
            name.strip() for name in args.class_names.split(",") if name.strip()
        )
    if args.no_augment:
        values["augment"] = False
    if args.no_amp:
        values["use_amp"] = False
    if "class_names" in values:
        values["class_names"] = tuple(values["class_names"])

    config = BaselineConfig(**values)
    config.validate()
    return config


def run_self_test(arch: str = "fcos_resnet50_fpn") -> int:
    """Train one epoch on a tiny synthetic split, on CPU, and score it.

    Verifies the whole chain -- target conversion, forward, backward, checkpoint,
    decode, letterbox inverse, COCO scoring -- without the dataset or a GPU.
    """
    import tempfile

    from PIL import Image

    from agrinav.training.weeddet_train import _CocoSplitDataset

    with tempfile.TemporaryDirectory() as tmp:
        images_root = os.path.join(tmp, "images")
        os.makedirs(images_root)
        images, annotations = [], []
        for index in range(4):
            name = f"synthetic_{index}.jpg"
            Image.new("RGB", (128, 128), (40 + index * 20, 90, 60)).save(
                os.path.join(images_root, name), quality=95
            )
            images.append({"id": index, "file_name": name, "width": 128, "height": 128})
            annotations.append(
                {
                    "id": index * 2,
                    "image_id": index,
                    "category_id": 1,
                    "bbox": [10.0, 10.0, 40.0, 40.0],
                    "area": 1600.0,
                    "iscrowd": 0,
                }
            )
            annotations.append(
                {
                    "id": index * 2 + 1,
                    "image_id": index,
                    "category_id": 2,
                    "bbox": [70.0, 70.0, 30.0, 30.0],
                    "area": 900.0,
                    "iscrowd": 0,
                }
            )
        ann_file = os.path.join(tmp, "instances.coco.json")
        with open(ann_file, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "images": images,
                    "annotations": annotations,
                    "categories": [
                        {"id": 1, "name": "rice_protect"},
                        {"id": 2, "name": "weed_target"},
                    ],
                },
                handle,
            )

        config = BaselineConfig(
            arch=arch,
            init="scratch",
            img_size=64,
            batch_size=2,
            num_workers=0,
            num_epochs=1,
            use_amp=False,
            augment=False,
            val_ap_interval=1,
            warmup_iters=1,
        )
        dataset = _CocoSplitDataset(
            ann_file, images_root, config.class_names, img_size=config.img_size, augment=False
        )
        out_dir = os.path.join(tmp, "run")
        run = train(
            config,
            dataset,
            val_dataset=dataset,
            val_ann_file=ann_file,
            out_dir=out_dir,
            device="cpu",
        )

    print(json.dumps({k: v for k, v in run.items() if k != "epochs"}, indent=2, sort_keys=True))
    if run["best_epoch"] is None:
        print("SELF-TEST FAIL: no checkpoint was selected", file=sys.stderr)
        return 1
    print("SELF-TEST PASS: train -> checkpoint -> decode -> COCO score completed")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agrinav baseline-detector",
        description=(
            "Train a stock torchvision detector on the identical split and protocol, "
            "so the WeedDet number has something to be measured against."
        ),
    )
    parser.add_argument("--self-test", action="store_true", help="tiny synthetic CPU run and exit")
    parser.add_argument("--arch", default=None, choices=SUPPORTED_ARCHS)
    parser.add_argument("--init", default=None, choices=("coco", "imagenet", "scratch"))
    parser.add_argument("--config", default=None, help="YAML config; CLI flags win over it")
    parser.add_argument("--ann-file", default=None, help="training split COCO json")
    parser.add_argument("--images-root", default=None, help="dir file_name resolves against")
    parser.add_argument("--val-ann-file", default=None, help="validation split COCO json")
    parser.add_argument("--val-images-root", default=None)
    parser.add_argument("--out-dir", default=None, help="checkpoints and run.json go here")
    parser.add_argument("--class-names", default=None, help="comma list, in class-index order")
    parser.add_argument("--img-size", dest="img_size", type=int, default=None)
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=None)
    parser.add_argument("--num-workers", dest="num_workers", type=int, default=None)
    parser.add_argument("--epochs", dest="num_epochs", type=int, default=None)
    parser.add_argument("--base-lr", dest="base_lr", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--val-ap-interval", dest="val_ap_interval", type=int, default=None)
    parser.add_argument("--score-threshold", dest="score_threshold", type=float, default=None)
    parser.add_argument("--nms-iou", dest="nms_iou", type=float, default=None)
    parser.add_argument("--max-detections", dest="max_detections", type=int, default=None)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--device", default=None, help="cuda or cpu (default: cuda if available)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.self_test:
        return run_self_test(args.arch or "fcos_resnet50_fpn")

    missing = [
        flag
        for flag, value in (
            ("--ann-file", args.ann_file),
            ("--images-root", args.images_root),
            ("--out-dir", args.out_dir),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"missing required argument(s): {', '.join(missing)}")

    config = build_config(args)
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if args.device and args.device.startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit(
            f"--device {args.device!r} requested but CUDA is not available. Training a "
            "reference detector on CPU is valid but very slow -- pass --device cpu to "
            "accept that explicitly."
        )

    from agrinav.training.weeddet_train import _CocoSplitDataset

    train_dataset = _CocoSplitDataset(
        args.ann_file,
        args.images_root,
        config.class_names,
        img_size=config.img_size,
        augment=config.augment,
    )
    val_dataset = None
    if args.val_ann_file or args.val_images_root:
        if not (args.val_ann_file and args.val_images_root):
            raise SystemExit("--val-ann-file and --val-images-root must be given together")
        val_dataset = _CocoSplitDataset(
            args.val_ann_file,
            args.val_images_root,
            config.class_names,
            img_size=config.img_size,
            augment=False,
        )

    print(f"baseline: {config.arch} init={config.init} device={device}")
    print(
        f"train {len(train_dataset)} images" + (f", val {len(val_dataset)}" if val_dataset else "")
    )

    run = train(
        config,
        train_dataset,
        val_dataset=val_dataset,
        val_ann_file=args.val_ann_file,
        out_dir=args.out_dir,
        device=device,
    )
    if run["best_epoch"] is not None:
        print(f"\nbest val/AP {run['best_val_ap']:.4f} at epoch {run['best_epoch']}")
    else:
        print(f"\n{run['warning']}")
    print(f"run record -> {os.path.join(args.out_dir, 'run.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
