"""weeddet_train.py -- exploratory detector training entrypoint (COCO split -> WeedDet).

This is the Phase-2 detector *driver*. It owns no model, loss, or training-loop
logic: it adapts the sealed split COCO files onto ``WeedDet`` and calls the
monolith's :func:`train_with_progress` via a small injected-dataset seam.

Scope (deliberately narrow -- "exploratory first"):
  * Goal of the first GPU run is loss convergence + qualitative val predictions,
    NOT a mAP number. There is no COCO evaluator here on purpose.
  * The **test split is sealed**: this module never opens ``test.coco.json``.
    Selection happens on train/val only.

Why an adapter dataset instead of reusing ``CocoWeedDataset`` directly: the split
JSONs are not co-located with their images. Each image record's ``file_name`` is
archive-relative (e.g. ``global rice segmentation/China/GD/rgb/IMG_5014_..jpg``),
so the on-disk path is ``os.path.join(images_root, file_name)`` where
``images_root`` is the extracted ``RiceSEG.zip`` root. ``_CocoSplitDataset``
overrides only the annotation-file location and path resolution; every other
behaviour (category-name->index map, letterbox, per-axis box scaling,
label-aligned augmentation) is inherited from ``CocoWeedDataset``.

CLI:
    python -m agrinav.training.weeddet_train --self-test
    python -m agrinav.training.weeddet_train \
        --ann-file artifacts/detector_v1/split_v1/train.coco.json \
        --images-root /path/to/RiceSEG --overfit 8 --batch-size 2 --no-pretrained-backbone
    python -m agrinav.training.weeddet_train \
        --ann-file .../split_v1/train.coco.json --images-root /content/riceseg \
        --config configs/training/detector_gpu.yaml \
        --checkpoint-dir runs/weeddet_baseline
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from agrinav.inference.postprocess import invert_letterbox


# ---------------------------------------------------------------- import WeedDet
def _import_wd() -> Any:
    """Import the WeedDet monolith, tolerating both the installed package and a
    bare-``models``/direct-script layout (mirrors ``riceseg_pretrain._import_wd``)."""
    here = Path(__file__).resolve().parent
    for candidate in (str(here.parent), str(here.parent / "models"), str(here)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    for name in ("agrinav.models.weeddet_v6b", "models.weeddet_v6b", "weeddet_v6b"):
        try:
            return __import__(name, fromlist=["x"])
        except ImportError:
            continue
    raise ImportError("weeddet_v6b.py not importable -- put it in models/ or on sys.path")


_WD = _import_wd()

# The three detector categories in the split JSONs, in canonical label order.
# COCO category ids are non-contiguous ({1,2,4}); the parent maps by *name* to
# contiguous indices in this order, so this tuple defines the class map.
DEFAULT_CLASS_NAMES: tuple[str, ...] = ("rice_protect", "weed_target", "non_target_aquatic")

# Effective defaults for every ``train_with_progress`` config key this driver
# owns. A YAML ``--config`` seeds over these; explicit CLI flags override both.
# ``num_classes`` is intentionally absent -- it is derived from ``class_names``.
_HARD_DEFAULTS: dict[str, Any] = {
    "device": None,  # resolved to 'cuda'/'cpu' in build_config
    "seed": 42,
    "deterministic": False,
    "anchor_base_scale": 3,
    "lsc_k": 7,
    "use_atss": True,
    "pretrained_backbone": True,
    "riceseg_backbone": None,  # path to a RiceSEG backbone .pth; overrides ImageNet
    "img_size": 512,
    "batch_size": 4,
    "num_workers": 2,
    "base_lr": 0.001,
    "momentum": 0.9,
    "weight_decay": 1e-4,
    "num_epochs": 12,
    "save_every": 4,
    "repeat_factor": 1,
    "min_lr": 1e-5,
    "warmup_factor": 0.001,
    "use_amp": None,  # None -> resolved to cuda-availability
    "use_ema": True,
    "ema_decay": 0.999,
    "grad_clip": 0.5,
    "checkpoint_dir": "checkpoints/weeddet",
    "class_names": list(DEFAULT_CLASS_NAMES),
    "augment": True,
    # Held-out validation. When both are set, the per-epoch val loss (of the
    # EMA weights, i.e. the ones actually saved) selects the best checkpoint
    # instead of the training loss.
    "val_ann_file": None,
    "val_images_root": None,
    "val_batch_size": None,
    # Epochs between validation-AP evaluations; 0 selects on val loss instead.
    # AP is the metric that actually describes detection quality -- loss can
    # improve while detections get worse -- but it needs the canonical decode
    # over the whole val split, so its cost is made explicit rather than hidden.
    "val_ap_interval": 0,
    # 'auto' keeps the historical coupling (freeze BN for ImageNet, trainable
    # for an injected backbone); set explicitly to make the A/B single-factor.
    "bn_policy": "auto",
    # Fail-closed assertion on WHICH BatchNorm layers the freeze covers. None
    # derives it from whichever loader ran ('backbone' for an injected backbone,
    # 'imagenet' otherwise); training aborts on a mismatch. Without this, the
    # name-list predicate silently froze 48 of 57 backbone BN under
    # --riceseg-backbone while reporting the policy as applied (2026-07-31).
    "bn_freeze_scope": None,
    # Fixed unaugmented images used each epoch for the train-mode vs eval-mode
    # BatchNorm confidence comparison. 0 disables. Buffers are snapshotted and
    # restored, so this observes training without altering it.
    "parity_probe_images": 8,
    # Write every pre-clip gradient norm, not just the per-epoch quantiles.
    "dump_grad_norms": False,
    # Full training-state resume. None starts from epoch 1; 'auto' continues from
    # <checkpoint_dir>/weeddet_last.pth when one exists; an explicit path resumes
    # from that file. Every epoch already wrote the optimizer, both schedulers and
    # the AMP scaler -- nothing read them back, so a reclaimed Colab VM cost the
    # whole run (2026-07-30: killed at batch 224/225 of epoch 15, 14 epochs lost).
    "resume": None,
    # Progress-bar redraw interval, seconds. Bars previously redrew every batch
    # and flooded the Colab cell with ~424k characters.
    "progress_interval": 2.0,
    "no_progress": False,
}

# Keys a YAML config may set. Unknown keys are rejected so typos fail loudly
# rather than being silently ignored (CLAUDE.md config policy).
_VALID_CONFIG_KEYS: frozenset[str] = frozenset(_HARD_DEFAULTS) | frozenset({"warmup_iters"})

# argparse attribute -> config key, for the layered CLI-override merge.
_CLI_TO_CONFIG: dict[str, str] = {
    "ann_file": "ann_file",
    "images_root": "images_root",
    "class_names": "class_names",
    "riceseg_backbone": "riceseg_backbone",
    "img_size": "img_size",
    "batch_size": "batch_size",
    "epochs": "num_epochs",
    "base_lr": "base_lr",
    "checkpoint_dir": "checkpoint_dir",
    "num_workers": "num_workers",
    "save_every": "save_every",
    "repeat_factor": "repeat_factor",
    "device": "device",
    "seed": "seed",
    "val_ann_file": "val_ann_file",
    "val_images_root": "val_images_root",
    "val_batch_size": "val_batch_size",
    "val_ap_interval": "val_ap_interval",
    "bn_policy": "bn_policy",
    "bn_freeze_scope": "bn_freeze_scope",
    "parity_probe_images": "parity_probe_images",
    "dump_grad_norms": "dump_grad_norms",
    "grad_clip": "grad_clip",
    "resume": "resume",
}


# ================================================================ dataset adapter
class _CocoSplitDataset(_WD.CocoWeedDataset):  # type: ignore[misc, name-defined]
    """A ``CocoWeedDataset`` whose annotations and images live apart.

    Loads a split COCO JSON from an explicit ``ann_file`` and resolves each image
    as ``os.path.join(images_root, file_name)``. Achieved by reusing the parent's
    path convention -- it joins ``(root, split, file_name)`` -- with ``split=''``,
    so ``__getitem__`` and ``items()`` are inherited unchanged and still exercise
    the parent letterbox / per-axis scaling / label-aligned augmentation. Only the
    constructor (ann-file loading + path roots, plus an optional ``limit``) differs.
    """

    def __init__(
        self,
        ann_file: str | os.PathLike[str],
        images_root: str | os.PathLike[str],
        class_names: tuple[str, ...],
        img_size: int = 512,
        augment: bool = False,
        limit: int | None = None,
    ) -> None:
        from PIL import Image as PILImage

        ann_file = os.fspath(ann_file)
        images_root = os.fspath(images_root)
        if not os.path.isfile(ann_file):
            raise FileNotFoundError(
                f"annotation file not found: {ann_file!r}. Pass --ann-file pointing at a "
                "split COCO json, e.g. artifacts/detector_v1/split_v1/train.coco.json "
                "(never test.coco.json -- that split is sealed)."
            )
        if not os.path.isdir(images_root):
            raise NotADirectoryError(
                f"images root not found: {images_root!r}. Extract RiceSEG.zip and pass "
                "--images-root pointing at its root so images_root + file_name resolves "
                "(e.g. /content/riceseg)."
            )

        self.PILImage = PILImage
        # split='' reduces the parent's os.path.join(root, split, file_name) to
        # os.path.join(images_root, file_name), matching the archive-relative file_name.
        self.root, self.split = images_root, ""
        self.img_size, self.augment = img_size, augment
        self.CLASS_NAMES = list(class_names)
        self.class_to_idx = {name: idx for idx, name in enumerate(self.CLASS_NAMES)}
        self.ann_file = ann_file

        with open(ann_file, encoding="utf-8") as handle:
            coco = json.load(handle)

        name_by_id = {c["id"]: c["name"] for c in coco["categories"]}
        self.catid_to_idx = {
            cid: self.class_to_idx[name]
            for cid, name in name_by_id.items()
            if name in self.class_to_idx
        }
        if not self.catid_to_idx:
            raise ValueError(
                f"none of class_names {tuple(class_names)} match categories in "
                f"{ann_file}: {sorted(name_by_id.values())}"
            )

        images = coco["images"]
        self.images = images[:limit] if limit is not None else images
        kept_ids = {im["id"] for im in self.images}
        self.anns_by_img: dict[Any, list[dict[str, Any]]] = {}
        for ann in coco["annotations"]:
            if ann["category_id"] in self.catid_to_idx and ann["image_id"] in kept_ids:
                self.anns_by_img.setdefault(ann["image_id"], []).append(ann)

        self.transform = _WD.T.Compose(
            [
                _WD.T.ToTensor(),
                _WD.T.Normalize(mean=_WD.IMAGENET_MEAN, std=_WD.IMAGENET_STD),
            ]
        )

    # train_with_progress pickles the whole config (this dataset included) into
    # every checkpoint. The parent stores the PIL.Image *module* on the instance,
    # which pickle cannot serialise ("cannot pickle 'module' object"). Drop it on
    # the way out and re-import it on the way in so the object round-trips and the
    # checkpoint save never fails.
    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        state.pop("PILImage", None)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        from PIL import Image as PILImage

        self.__dict__.update(state)
        self.PILImage = PILImage


# ================================================================ config building
def parse_class_names(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Normalise a comma string or sequence into a non-empty tuple of class names."""
    if isinstance(value, str):
        names = [part.strip() for part in value.split(",") if part.strip()]
    else:
        names = [str(part).strip() for part in value if str(part).strip()]
    if not names:
        raise ValueError("--class-names resolved to an empty list")
    return tuple(names)


def _resolve_device(name: str | None) -> str:
    """Concrete device string; downgrades a requested CUDA device to CPU if absent."""
    if name and name.lower().startswith("cuda") and not torch.cuda.is_available():
        return "cpu"
    if name:
        return name
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_yaml_config(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a YAML config, rejecting unknown keys so typos fail loudly."""
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"--config file not found: {path!r}")
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "--config requires PyYAML (pip install pyyaml), or omit --config and pass "
            "hyperparameters as CLI flags instead."
        ) from exc
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config {path!r} must be a YAML mapping, got {type(data).__name__}")
    unknown = sorted(set(data) - _VALID_CONFIG_KEYS)
    if unknown:
        raise ValueError(
            f"config {path!r} has unrecognised key(s): {unknown}. "
            f"Allowed keys: {sorted(_VALID_CONFIG_KEYS)}"
        )
    return data


def _cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Config keys explicitly supplied on the CLI (skip the unset ``None`` defaults)."""
    overrides: dict[str, Any] = {}
    for attr, key in _CLI_TO_CONFIG.items():
        value = getattr(args, attr, None)
        if value is not None:
            overrides[key] = value
    return overrides


def _resolve_pretrained(cfg: dict[str, Any], args: argparse.Namespace) -> bool:
    """``--no-pretrained-backbone`` forces off; otherwise config/default wins."""
    if getattr(args, "no_pretrained_backbone", False):
        return False
    return bool(cfg.get("pretrained_backbone", True))


class _RicesegBackboneInit:
    """Picklable ``backbone_init`` callable: load a RiceSEG backbone into WeedDet.

    A plain closure would be simpler but the whole config is pickled into every
    checkpoint by ``train_with_progress``; a module-level class survives that
    round-trip. Only the checkpoint *path* is stored, so the pickle stays tiny.

    Delegates to :func:`agrinav.training.riceseg_pretrain.load_riceseg_backbone`,
    which fails closed: every expected ``backbone.*`` tensor must be present with
    a matching shape or it raises rather than silently training from a mostly
    random backbone (deep audit 2026-07-20 §9.4).

    BN is deliberately left trainable — the loaded running stats are in-domain,
    and ``apply_bn_policy`` (which freezes BN where ImageNet stats exist) must not
    be applied on top. The monolith's seam skips it whenever this is injected.
    """

    def __init__(self, ckpt_path: str) -> None:
        self.ckpt_path = os.fspath(ckpt_path)

    def __call__(self, model: Any) -> int:
        from agrinav.training.riceseg_pretrain import load_riceseg_backbone

        n = load_riceseg_backbone(model, self.ckpt_path, verbose=True)
        print(
            f"[backbone] RiceSEG init from {self.ckpt_path} "
            "(ImageNet skipped; BN left trainable)"
        )
        return n

    def __repr__(self) -> str:  # keeps the saved config readable
        return f"{type(self).__name__}({self.ckpt_path!r})"


def _make_riceseg_backbone_init(ckpt_path: str) -> _RicesegBackboneInit:
    """Validate the checkpoint path now, so a typo fails before training starts."""
    path = os.fspath(ckpt_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"--riceseg-backbone checkpoint not found: {path!r}. Pass the backbone "
            "exported by `agrinav pretrain` (e.g. .../out/riceseg_backbone.pth), or "
            "omit the flag to warm-start from ImageNet instead."
        )
    return _RicesegBackboneInit(path)


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    """Assemble the ``train_with_progress`` config for a full training run.

    Merge order (last wins): hard defaults < ``--config`` YAML < explicit CLI flags.
    ``num_classes`` is derived from ``class_names`` and the injected
    ``train_dataset`` is a :class:`_CocoSplitDataset` over ``--ann-file``. When
    ``riceseg_backbone`` is set, a picklable ``backbone_init`` callable is added
    so ``train_with_progress`` loads that in-domain backbone in place of ImageNet.
    """
    _require_data_args(args)
    cfg: dict[str, Any] = dict(_HARD_DEFAULTS)
    if getattr(args, "config", None):
        cfg.update(_load_yaml_config(args.config))
    cfg.update(_cli_overrides(args))

    class_names = parse_class_names(cfg["class_names"])
    cfg["class_names"] = list(class_names)
    cfg["num_classes"] = len(class_names)
    cfg["device"] = _resolve_device(cfg.get("device"))
    cfg["pretrained_backbone"] = _resolve_pretrained(cfg, args)
    if cfg.get("use_amp") is None:
        cfg["use_amp"] = torch.cuda.is_available()
    # `_HARD_DEFAULTS` uses None to mean "same as training". Leaving that
    # sentinel unresolved disables DataLoader automatic batching and sends a
    # raw `(image, target)` sample into the list-based collate function.
    if cfg.get("val_batch_size") is None:
        cfg["val_batch_size"] = cfg["batch_size"]

    if cfg.get("riceseg_backbone"):
        cfg["backbone_init"] = _make_riceseg_backbone_init(cfg["riceseg_backbone"])
        # The injected loader replaces ImageNet; the monolith's backbone seam
        # ignores pretrained_backbone when backbone_init is present, but record
        # it False so the saved config is unambiguous.
        cfg["pretrained_backbone"] = False

    cfg["train_dataset"] = _CocoSplitDataset(
        cfg["ann_file"],
        cfg["images_root"],
        class_names,
        img_size=cfg["img_size"],
        augment=bool(cfg.get("augment", True)),
    )

    val_ann, val_root = cfg.get("val_ann_file"), cfg.get("val_images_root")
    if bool(val_ann) != bool(val_root):
        raise ValueError(
            "--val-ann-file and --val-images-root must be given together "
            f"(got val_ann_file={val_ann!r}, val_images_root={val_root!r})."
        )
    if val_ann is not None and val_root is not None:
        val_ann, val_root = os.fspath(val_ann), os.fspath(val_root)
        if os.path.basename(val_ann).startswith("test"):
            raise ValueError(
                f"refusing to validate on {val_ann!r}: the test split is sealed and "
                "must never drive checkpoint selection or threshold choice "
                "(CLAUDE.md 13.3). Pass the valid split instead."
            )
        # augment=False: validation must score the model, not the augmentation.
        cfg["val_dataset"] = _CocoSplitDataset(
            val_ann, val_root, class_names, img_size=cfg["img_size"], augment=False
        )
    return cfg


# ================================================================ modes
def run_self_test(img_size: int = 128) -> int:
    """One forward+backward on synthetic data. No dataset, no network.

    Builds ``WeedDet(num_classes=3)`` and a 2-image batch of random tensors: one
    image with two random boxes, one with **zero** GT (exercises the empty-target
    branch of the loss). Asserts every loss is finite and ``total_loss``
    backpropagates to finite gradients.
    """
    torch.manual_seed(0)
    model = _WD.WeedDet(num_classes=3)
    model.train()

    images = torch.randn(2, 3, img_size, img_size)
    targets = [
        {
            "boxes": torch.tensor([[10.0, 10.0, 50.0, 50.0], [60.0, 60.0, 110.0, 110.0]]),
            "labels": torch.tensor([0, 2], dtype=torch.int64),
        },
        {
            "boxes": torch.zeros((0, 4), dtype=torch.float32),
            "labels": torch.zeros((0,), dtype=torch.int64),
        },
    ]

    losses = model(images, targets)
    for key, value in losses.items():
        if not torch.isfinite(value).all():
            raise ValueError(f"[self-test] non-finite loss {key}={value}")
    total = losses["total_loss"]
    total.backward()

    grads = [p.grad for p in model.parameters() if p.grad is not None]
    if not grads:
        raise ValueError("[self-test] no gradients produced by total_loss.backward()")
    if not all(torch.isfinite(g).all() for g in grads):
        raise ValueError("[self-test] non-finite gradients")

    reported = {k: round(float(v.detach()), 4) for k, v in losses.items()}
    print(f"[self-test] losses={reported} | {len(grads)} grad tensors, all finite. PASS")
    return 0


def _subset_coco_gt(dataset: Any) -> dict[str, Any]:
    """In-memory COCO ground truth covering exactly the images a dataset kept.

    ``_CocoSplitDataset(limit=N)`` truncates ``self.images`` and filters
    ``anns_by_img`` to match, but the file on disk still describes the whole
    split. Scoring N memorised images against the full annotation file counts
    every unscored image as a miss, so recall would be pinned near ``N/total``
    and the gate would measure the subset size rather than the model.
    """
    with open(dataset.ann_file, encoding="utf-8") as handle:
        source = json.load(handle)
    annotations: list[dict[str, Any]] = []
    for image in dataset.images:
        annotations.extend(dataset.anns_by_img.get(image["id"], []))
    return {
        "images": list(dataset.images),
        "annotations": annotations,
        "categories": source["categories"],
    }


def run_overfit(args: argparse.Namespace) -> int:
    """Smoke gate: memorise the first N train images, then score the DECODED output.

    ``pretrained_backbone`` stays off unless a CUDA device is present (the ImageNet
    loader fails closed offline). Runs a compact SGD loop that exercises the real
    ``WeedDet`` forward/backward through the injected ``_CocoSplitDataset`` +
    ``collate_fn``.

    The gate is eval-mode AP50 and recall over the same images, plus train/eval
    BatchNorm confidence parity — not ``final_loss < initial_loss``. That old
    condition passed for the 2026-07-28 checkpoints, whose loss fell for 14
    epochs and which then scored AP 0.0000 / AP50 0.0001 in eval mode: the
    classification head had learned (0.9367 peak confidence under batch
    statistics) but the running statistics it was evaluated with had not. A gate
    that never decodes a box, and never runs the model in the mode it will be
    deployed in, cannot see that failure. This one runs the real postprocessor
    through the real COCO evaluator on the real eval path.
    """
    _require_data_args(args)
    if args.overfit <= 0:
        raise ValueError("--overfit expects a positive image count")

    class_names = parse_class_names(args.class_names or DEFAULT_CLASS_NAMES)
    device = torch.device(_resolve_device(args.device))
    img_size = args.img_size or 512
    seed = args.seed if args.seed is not None else 42
    _WD.set_seed(seed, deterministic=True)

    dataset = _CocoSplitDataset(
        args.ann_file,
        args.images_root,
        class_names,
        img_size=img_size,
        augment=False,
        limit=args.overfit,
    )
    if len(dataset) == 0:
        raise ValueError(f"overfit dataset is empty for --ann-file {args.ann_file!r}")

    batch_size = min(args.batch_size or 2, len(dataset))
    loader: DataLoader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=_WD.collate_fn,
        num_workers=0,
    )

    pretrained = (not args.no_pretrained_backbone) and torch.cuda.is_available()
    model = _WD.WeedDet(num_classes=len(class_names)).to(device)
    if pretrained:
        _WD.load_imagenet_backbone(model)
    bn_scope = "imagenet" if pretrained else None
    # Resolved once, before the first step: the predicate reads BN buffers, and
    # after one epoch a randomly initialised BN no longer looks randomly
    # initialised.
    bn_freeze_names = _WD.resolve_bn_freeze_names(
        model, pretrained_loaded=pretrained, expect_scope=bn_scope
    )
    frozen, trainable = _WD.apply_bn_policy(model, freeze_names=bn_freeze_names)
    print(f"[overfit] bn frozen={frozen} trainable={trainable} scope={bn_scope}")

    optimizer = torch.optim.SGD(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.base_lr or 0.01,
        momentum=0.9,
        weight_decay=1e-4,
    )
    epochs = args.epochs or 60
    print(
        f"[overfit] {len(dataset)} images | bs={batch_size} | epochs={epochs} | "
        f"device={device.type} | pretrained_backbone={pretrained}"
    )

    def reapply_policy() -> None:
        _WD.apply_bn_policy(model, freeze_names=bn_freeze_names)

    # Same threshold the real training loop uses, so the clipped-fraction this
    # prints is evidence about that run and not about a literal local to here.
    # `or` would send an explicit --grad-clip 0 (meaning "disable") back to the
    # 0.5 default, so test for None rather than falsiness.
    _requested_clip = getattr(args, "grad_clip", None)
    if _requested_clip is None:
        _requested_clip = _HARD_DEFAULTS["grad_clip"]
    grad_clip = float(_requested_clip)
    # A non-positive clip means "do not clip". inf keeps clip_grad_norm_'s return
    # value -- the true pre-clip norm -- so the distribution is still recorded.
    clip_norm = grad_clip if grad_clip > 0 else float("inf")

    initial_loss: float | None = None
    final_loss = float("nan")
    grad_norms: list[float] = []
    for epoch in range(1, epochs + 1):
        model.train()
        reapply_policy()
        running, n_batches = 0.0, 0
        cls_pos = cls_neg = 0.0
        for images, targets in loader:
            if not isinstance(images, torch.Tensor):
                continue
            images = images.to(device)
            targets = [
                {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in t.items()}
                for t in targets
            ]
            optimizer.zero_grad(set_to_none=True)
            losses = model(images, targets)
            loss = losses["total_loss"]
            loss.backward()
            total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), clip_norm)
            grad_norms.append(float(total_norm))
            optimizer.step()
            running += float(loss.item())
            cls_pos += float(losses["cls_loss_pos"])
            cls_neg += float(losses["cls_loss_neg"])
            n_batches += 1
        avg = running / max(n_batches, 1)
        if initial_loss is None:
            initial_loss = avg
        final_loss = avg
        print(
            f"[overfit] epoch {epoch:03d}/{epochs}  avg_loss={avg:.4f}  "
            f"cls_pos={cls_pos / max(n_batches, 1):.4f}  "
            f"cls_neg={cls_neg / max(n_batches, 1):.4f}"
        )

    if grad_norms:
        norms = torch.tensor(grad_norms)
        p50, p90, p99 = (float(v) for v in torch.quantile(norms, torch.tensor([0.5, 0.9, 0.99])))
        clipped = float((norms > clip_norm).float().mean())
        print(
            f"[overfit] grad_norm p50={p50:.3f} p90={p90:.3f} p99={p99:.3f} "
            f"max={float(norms.max()):.3f} | clipped {clipped * 100:.1f}% at "
            f"{grad_clip if grad_clip > 0 else 'disabled'}"
        )

    # --- the gate: decoded detections on the eval path, not the loss curve -----
    from agrinav.evaluation.metrics import evaluate_coco_detections
    from agrinav.evaluation.runner import predict_split

    # Capped: --overfit accepts any N, and 64 images at 512px is ~200 MB of
    # activations for a diagnostic. 8 is enough to compare two modes.
    n_probe = min(len(dataset), max(1, args.parity_probe_images or 8))
    probe = torch.stack([dataset[i][0] for i in range(n_probe)]).to(device)
    parity = _WD.train_eval_confidence_parity(model, probe, reapply_policy=reapply_policy)

    detections = predict_split(
        model, dataset, device=str(device), img_size=img_size, batch_size=batch_size
    )
    result = evaluate_coco_detections(_subset_coco_gt(dataset), detections)

    ratio = parity["parity/max_conf_ratio"]
    print(
        f"[overfit] decoded: AP={result.ap:.4f} AP50={result.ap50:.4f} "
        f"AR100={result.ar_100:.4f} dets={result.num_detections} "
        f"gt={result.num_gt_annotations}"
    )
    print(
        f"[overfit] bn parity: train_max={parity['parity/train_max_conf']:.4f} "
        f"eval_max={parity['parity/eval_max_conf']:.4f} ratio={ratio:.2f}"
    )

    failures: list[str] = []
    if result.ap50 < args.overfit_min_ap50:
        failures.append(f"AP50 {result.ap50:.4f} < {args.overfit_min_ap50}")
    if result.ar_100 < args.overfit_min_recall:
        failures.append(f"AR100 {result.ar_100:.4f} < {args.overfit_min_recall}")
    if not 1.0 / args.overfit_max_conf_ratio <= ratio <= args.overfit_max_conf_ratio:
        failures.append(
            f"train/eval confidence ratio {ratio:.2f} outside "
            f"[{1.0 / args.overfit_max_conf_ratio:.2f}, {args.overfit_max_conf_ratio:.2f}]"
        )
    # Kept as a secondary signal: informative, but on its own it passed a run
    # that could not decode a single box.
    if initial_loss is None or not (final_loss < initial_loss):
        failures.append(f"loss did not drop ({initial_loss} -> {final_loss})")

    if failures:
        print("[overfit] FAILED: " + "; ".join(failures))
        return 1
    print(
        f"[overfit] PASSED: AP50={result.ap50:.4f} AR100={result.ar_100:.4f} "
        f"conf_ratio={ratio:.2f} loss {initial_loss:.4f} -> {final_loss:.4f}"
    )
    return 0


# ================================================================ inference helpers
def _alias_legacy_pickle_names() -> None:
    """Republish this module's picklable helpers under ``__main__``.

    Training is launched as ``python -m agrinav.training.weeddet_train``, which
    executes this module *as* ``__main__``. Any instance pickled into a
    checkpoint therefore records ``__main__._RicesegBackboneInit`` rather than
    the importable path. Loading such a checkpoint from a notebook, a test, or
    the evaluation CLI fails with ``AttributeError`` because that name does not
    exist in *their* ``__main__``. Binding the names here makes the historical
    checkpoints loadable; new checkpoints avoid the problem entirely by not
    pickling these objects at all (see ``sanitize_config_for_save``).
    """
    import __main__

    for obj in (_RicesegBackboneInit, _CocoSplitDataset):
        if not hasattr(__main__, obj.__name__):
            setattr(__main__, obj.__name__, obj)


def load_checkpoint_model(
    checkpoint_path: str | os.PathLike[str],
    num_classes: int | None = None,
    device: str = "cpu",
) -> Any:
    """Load a ``WeedDet`` from a ``train_with_progress`` checkpoint for eval-mode use.

    Reads the EMA ``state_dict`` (falls back to the raw model state) and infers
    ``num_classes`` from the saved config when not given. Used by the Colab
    qualitative cell so the notebook redefines no model logic.

    Checkpoints written since the config-sanitising fix load under
    ``weights_only=True``. Older ones embedded the live training config -- the
    ``_CocoSplitDataset`` and the ``_RicesegBackboneInit`` callable -- so they
    need full unpickling. Worse, because training runs as
    ``python -m agrinav.training.weeddet_train``, that module *is* ``__main__``,
    so those classes pickled with ``__module__ == '__main__'`` and unpickling
    them anywhere else raised ``AttributeError: Can't get attribute
    '_RicesegBackboneInit' on <module '__main__'>``. :func:`_alias_legacy_pickle_names`
    republishes them under ``__main__`` so the historical artifacts stay readable.
    """
    import pickle

    path = os.fspath(checkpoint_path)
    try:
        checkpoint = torch.load(path, map_location=device, weights_only=True)
    except (pickle.UnpicklingError, RuntimeError, AttributeError):
        _alias_legacy_pickle_names()
        checkpoint = torch.load(path, map_location=device, weights_only=False)
    if num_classes is None:
        num_classes = int(checkpoint.get("config", {}).get("num_classes", 1))
    model = _WD.WeedDet(num_classes=num_classes)
    state = checkpoint.get("state_dict", checkpoint)
    model.load_state_dict(state)
    model.to(device).eval()
    return model


def predict_image(
    model: Any,
    image_path: str | os.PathLike[str],
    img_size: int = 512,
    device: str = "cpu",
    score_thr: float = 0.3,
) -> tuple[Any, Any, Any, Any]:
    """Run eval-mode detection on one image; return (PIL image, boxes, scores, labels).

    Boxes are mapped back to original-image pixel coordinates via the exact
    inverse letterbox transform. Filtering at ``score_thr`` is for visual triage
    only -- this is exploratory, not a calibrated operating point.
    """
    from PIL import Image

    img = Image.open(os.fspath(image_path)).convert("RGB")
    letterboxed, scale_x, scale_y, pad_left, pad_top = _WD.letterbox_pil(img, img_size)
    transform = _WD.T.Compose(
        [
            _WD.T.ToTensor(),
            _WD.T.Normalize(mean=_WD.IMAGENET_MEAN, std=_WD.IMAGENET_STD),
        ]
    )
    tensor = transform(letterboxed).unsqueeze(0).to(device)

    model.eval()
    with torch.no_grad():
        detections = model(tensor)[0]
    boxes = detections["boxes"].detach().cpu()
    scores = detections["scores"].detach().cpu()
    labels = detections["labels"].detach().cpu()

    keep = scores >= score_thr
    boxes, scores, labels = boxes[keep], scores[keep], labels[keep]
    if len(boxes):
        # Clip to the original image: a detection that reached into the grey
        # letterbox padding otherwise comes back with negative coordinates.
        boxes, inside = invert_letterbox(
            boxes, scale_x, scale_y, pad_left, pad_top, orig_w=img.width, orig_h=img.height
        )
        boxes, scores, labels = boxes[inside], scores[inside], labels[inside]
    return img, boxes.numpy(), scores.numpy(), labels.numpy()


# ================================================================ CLI
def _require_data_args(args: argparse.Namespace) -> None:
    """Fail with an actionable message when data paths are needed but missing."""
    missing = [
        flag
        for flag, value in (("--ann-file", args.ann_file), ("--images-root", args.images_root))
        if not value
    ]
    if missing:
        raise SystemExit(
            f"missing required argument(s): {', '.join(missing)}. Provide the TRAIN split "
            "COCO json and the extracted images root, e.g. --ann-file "
            "artifacts/detector_v1/split_v1/train.coco.json --images-root /path/to/RiceSEG. "
            "(Use --self-test for a no-data smoke check.)"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agrinav train-detector",
        description=(
            "Exploratory WeedDet detector training on a COCO split "
            "(loss convergence + qualitative val predictions; the test split is sealed)."
        ),
    )
    parser.add_argument(
        "--ann-file", help="path to the TRAIN split COCO json (never test.coco.json)"
    )
    parser.add_argument(
        "--images-root",
        help="directory joined with each record's file_name (extracted RiceSEG root)",
    )
    parser.add_argument(
        "--val-ann-file",
        default=None,
        help="path to the VALID split COCO json; enables a per-epoch held-out "
        "val loss that selects the best checkpoint (never test.coco.json)",
    )
    parser.add_argument(
        "--val-images-root",
        default=None,
        help="images root for --val-ann-file (required with it)",
    )
    parser.add_argument(
        "--val-batch-size",
        type=int,
        default=None,
        help="validation images per step (default: same as --batch-size)",
    )
    parser.add_argument(
        "--val-ap-interval",
        type=int,
        default=None,
        help="epochs between validation-AP evaluations; selects `best` on COCO AP "
        "instead of val loss. 0 (default) keeps val-loss selection. Requires "
        "--val-ann-file/--val-images-root",
    )
    parser.add_argument(
        "--bn-policy",
        default=None,
        choices=("auto", "freeze_pretrained", "trainable"),
        help="BatchNorm treatment. 'auto' (default) freezes BN where ImageNet "
        "stats exist and leaves it trainable for an injected backbone; set it "
        "explicitly to keep an ImageNet-vs-RiceSEG A/B single-factor",
    )
    parser.add_argument(
        "--bn-freeze-scope",
        default=None,
        choices=("imagenet", "backbone"),
        help="which BatchNorm layers 'freeze_pretrained' must cover, as a "
        "fail-closed assertion. Defaults to 'backbone' (all 57 backbone BN) when "
        "--riceseg-backbone injects a full backbone, 'imagenet' (48) otherwise. "
        "Training aborts if the layers actually holding loaded statistics do not "
        "match, rather than silently freezing fewer",
    )
    parser.add_argument(
        "--parity-probe-images",
        type=int,
        default=None,
        help="fixed unaugmented images used each epoch to compare train-mode vs "
        "eval-mode BatchNorm confidence (default: 8; 0 disables). Costs two "
        "no-grad forwards per epoch and restores every BN buffer afterwards",
    )
    parser.add_argument(
        "--dump-grad-norms",
        action="store_true",
        # default=None, not False: _cli_overrides applies any non-None value, so
        # a plain False would override a YAML `dump_grad_norms: true`.
        default=None,
        help="also write the full per-step pre-clip gradient norms to "
        "<checkpoint-dir>/grad_norms_epochNNN.json (quantiles always go to "
        "metrics.jsonl)",
    )
    parser.add_argument(
        "--overfit-min-ap50",
        type=float,
        default=0.50,
        help="PROVISIONAL gate for --overfit: minimum eval-mode AP50 on the "
        "memorised images. 0.50 is set below the 0.6+ this configuration reached "
        "on overfit-16 under hard classification targets; it is a smoke floor, "
        "not a quality standard, and should be re-set from pilot evidence",
    )
    parser.add_argument(
        "--overfit-min-recall",
        type=float,
        default=0.50,
        help="PROVISIONAL gate for --overfit: minimum eval-mode AR@100. Separate "
        "from AP50 because a model can score decently on the few boxes it does "
        "emit while missing most objects",
    )
    parser.add_argument(
        "--overfit-max-conf-ratio",
        type=float,
        default=3.0,
        help="PROVISIONAL gate for --overfit: max train-mode/eval-mode peak "
        "confidence ratio (checked in both directions). The 2026-07-28 failure "
        "sat near 47x (0.9367 vs ~0.02); a memorised set should be near 1x",
    )
    parser.add_argument(
        "--resume",
        default=None,
        metavar="PATH|auto",
        help="continue a previous run: restores model, EMA, optimizer, both LR "
        "schedulers and the AMP scaler, and starts at the next epoch. 'auto' uses "
        "<checkpoint-dir>/weeddet_last.pth when present and starts from scratch "
        "otherwise. Refuses to resume across a different class map or a different "
        "checkpoint-selection metric. This is NOT --riceseg-backbone (weights only, "
        "fresh optimizer) -- the two modes are deliberately separate",
    )
    parser.add_argument(
        "--class-names",
        default=None,
        help="comma list mapped to contiguous label ids "
        f"(default: {','.join(DEFAULT_CLASS_NAMES)})",
    )
    parser.add_argument(
        "--img-size", type=int, default=None, help="square letterbox size (default: 512)"
    )
    parser.add_argument("--batch-size", type=int, default=None, help="images per step (default: 4)")
    parser.add_argument("--epochs", type=int, default=None, help="training epochs (default: 12)")
    parser.add_argument(
        "--base-lr", type=float, default=None, help="SGD base learning rate (default: 0.001)"
    )
    parser.add_argument(
        "--grad-clip",
        type=float,
        default=None,
        help="gradient-norm clip (default: 0.5). Pass 0 or a negative value to "
        "disable clipping entirely while still recording the norms. The default "
        "is not a safety net on this model: measured pre-clip norms run 65-120, "
        "so 0.5 truncates every step by ~130x and the clip, not the LR schedule, "
        "sets the effective step size.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="output dir for weeddet_best.pth (default: checkpoints/weeddet)",
    )
    parser.add_argument(
        "--num-workers", type=int, default=None, help="DataLoader workers (default: 2)"
    )
    parser.add_argument(
        "--save-every", type=int, default=None, help="periodic checkpoint epoch stride"
    )
    parser.add_argument("--repeat-factor", type=int, default=None, help="dataset repeats per epoch")
    parser.add_argument(
        "--no-pretrained-backbone",
        action="store_true",
        help="skip the ImageNet warm-start (required offline / on CPU)",
    )
    parser.add_argument(
        "--riceseg-backbone",
        default=None,
        metavar="PATH",
        help=(
            "warm-start from a RiceSEG-pretrained backbone (from `agrinav pretrain`) "
            "instead of ImageNet; fails closed on a partial/mismatched load"
        ),
    )
    parser.add_argument(
        "--device", default=None, help="cuda or cpu (default: cuda if available, else cpu)"
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (default: 42)")
    parser.add_argument(
        "--config", default=None, help="optional YAML seeding defaults; CLI flags override it"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--self-test",
        action="store_true",
        help="one forward+backward on synthetic data; no dataset, no network",
    )
    mode.add_argument(
        "--overfit",
        type=int,
        default=0,
        metavar="N",
        help=(
            "memorise the first N train images, then gate on decoded eval-mode "
            "detections over those same images: AP50, AR@100 and train-vs-eval "
            "BN confidence parity (see the --overfit-* thresholds). A falling "
            "loss is checked too, but only as a secondary signal — it passed for "
            "checkpoints that then decoded AP 0.0000"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int | None:
    """Dispatch to a mode. Returns a process exit code (0 = success)."""
    args = _build_parser().parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.overfit and args.overfit > 0:
        return run_overfit(args)

    config = build_config(args)
    _WD.train_with_progress(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
