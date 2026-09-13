#!/usr/bin/env python3
"""Model to COCO detections: the adapter that makes the evaluator usable.

The repository already had an honest ``pycocotools`` metric primitive
(:mod:`agrinav.evaluation.metrics`) and a detector. What it did not have was the
piece between them, so nothing in the training or inference stack ever produced
detections a metric could score, and checkpoints were selected on loss instead.

This module is that piece, and it is deliberately thin: it walks a split, runs
the canonical postprocessor (:mod:`agrinav.inference.postprocess`), inverts the
letterbox with clipping, maps class indices to COCO category ids, and hands the
result to the evaluator. Every protocol knob is an argument with a documented
default, recorded in the returned report, so two runs can be compared or shown
to be incomparable.

    agrinav evaluate-detector \\
        --checkpoint models/candidates/best.pth \\
        --ann-file  data/annotations/instances_valid.coco.json \\
        --images-root data/images/valid \\
        --out reports/metrics/valid_ap.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Mapping, Sequence

import torch

from agrinav.evaluation.metrics import CocoEvalResult, evaluate_coco_detections
from agrinav.inference.postprocess import (
    DEFAULT_MAX_DETECTIONS,
    DEFAULT_NMS_IOU,
    DEFAULT_PRE_NMS_TOPK,
    DEFAULT_SCORE_THRESHOLD,
    decode_batch,
    invert_letterbox,
    to_coco_detections,
)

# Batch size for the prediction sweep. Independent of the training batch size:
# no gradients are held, so this is bounded by activation memory only.
DEFAULT_EVAL_BATCH_SIZE = 8


class EvaluationError(RuntimeError):
    """Raised when predictions cannot be produced or scored correctly."""


def predict_split(
    model: Any,
    dataset: Any,
    *,
    device: str = "cpu",
    img_size: int = 512,
    batch_size: int = DEFAULT_EVAL_BATCH_SIZE,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    nms_iou: float = DEFAULT_NMS_IOU,
    max_detections: int = DEFAULT_MAX_DETECTIONS,
    use_soft_nms: bool = True,
    pre_nms_topk: int | None = DEFAULT_PRE_NMS_TOPK,
    index_to_category_id: Mapping[int, int] | None = None,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Run the detector over a split and return COCO-format detection records.

    Args:
        model: a ``WeedDet``. Put in ``eval()`` here; gradients are never taken.
        dataset: a ``_CocoSplitDataset``-shaped object exposing ``items()`` as
            ``[(image_id, path, width, height), ...]`` and ``catid_to_idx``.
        device: torch device string.
        img_size: letterbox size; must match what the checkpoint was trained at.
        batch_size: images per forward pass.
        score_threshold: pre-suppression candidate gate.
        nms_iou: suppression IoU, applied within a class.
        max_detections: per-image cap. Keep at 100 for a COCO-comparable number.
        use_soft_nms: Soft-NMS instead of hard NMS.
        pre_nms_topk: per-class candidate cap.
        index_to_category_id: model class index to COCO category id. Derived by
            inverting ``dataset.catid_to_idx`` when omitted.
        progress: print a line every 10 batches.

    Returns:
        COCO detection dicts, ready for :func:`evaluate_coco_detections`.

    Raises:
        EvaluationError: if the dataset exposes no items or no usable class map.
    """
    from PIL import Image

    import agrinav.models.weeddet_v6b as weeddet

    items = list(dataset.items())
    if not items:
        raise EvaluationError("dataset exposes no items(); nothing to evaluate")

    if index_to_category_id is None:
        catid_to_idx = getattr(dataset, "catid_to_idx", None)
        if not catid_to_idx:
            raise EvaluationError(
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
            for start in range(0, len(items), batch_size):
                batch = items[start : start + batch_size]
                tensors, geometry = [], []
                for _image_id, path, _width, _height in batch:
                    with Image.open(os.fspath(path)) as handle:
                        image = handle.convert("RGB")
                        original_size = image.size
                        letterboxed, scale_x, scale_y, pad_left, pad_top = weeddet.letterbox_pil(
                            image, img_size
                        )
                    tensors.append(transform(letterboxed))
                    geometry.append((scale_x, scale_y, pad_left, pad_top, original_size))

                images = torch.stack(tensors).to(device)
                cls_logits, regs, anchors, shape = model._get_logits(images)
                decoded = decode_batch(
                    cls_logits,
                    regs,
                    anchors,
                    shape,
                    num_classes=model.num_classes,
                    score_threshold=score_threshold,
                    nms_iou=nms_iou,
                    max_detections=max_detections,
                    use_soft_nms=use_soft_nms,
                    pre_nms_topk=pre_nms_topk,
                )

                for (image_id, _path, _w, _h), result, geom in zip(batch, decoded, geometry):
                    scale_x, scale_y, pad_left, pad_top, (orig_w, orig_h) = geom
                    boxes = result["boxes"].detach().cpu()
                    scores = result["scores"].detach().cpu()
                    labels = result["labels"].detach().cpu()
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

                if progress and (start // batch_size) % 10 == 0:
                    print(
                        f"  [eval] {min(start + batch_size, len(items))}/{len(items)} images, "
                        f"{len(detections)} detections",
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
    *,
    device: str = "cpu",
    img_size: int = 512,
    batch_size: int = DEFAULT_EVAL_BATCH_SIZE,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    nms_iou: float = DEFAULT_NMS_IOU,
    max_detections: int = DEFAULT_MAX_DETECTIONS,
    use_soft_nms: bool = True,
    pre_nms_topk: int | None = DEFAULT_PRE_NMS_TOPK,
    progress: bool = False,
) -> tuple[CocoEvalResult, list[dict[str, Any]], dict[str, Any]]:
    """Predict over a split and score it with ``pycocotools``.

    Returns:
        ``(result, detections, protocol)`` — the metrics, the raw detection
        records, and the exact protocol used. Always record ``protocol``
        alongside any number taken from ``result``: an AP produced with a
        different threshold, NMS, or ``max_detections`` is a different quantity.
    """
    started = time.time()
    detections = predict_split(
        model,
        dataset,
        device=device,
        img_size=img_size,
        batch_size=batch_size,
        score_threshold=score_threshold,
        nms_iou=nms_iou,
        max_detections=max_detections,
        use_soft_nms=use_soft_nms,
        pre_nms_topk=pre_nms_topk,
        progress=progress,
    )
    predict_seconds = time.time() - started

    result = evaluate_coco_detections(os.fspath(ann_file), detections, max_dets=max_detections)
    protocol = {
        "img_size": img_size,
        "score_threshold": score_threshold,
        "nms_iou": nms_iou,
        "max_detections": max_detections,
        "use_soft_nms": use_soft_nms,
        "pre_nms_topk": pre_nms_topk,
        "device": device,
        "is_standard_maxdets": result.is_standard_maxdets,
        "predict_seconds": round(predict_seconds, 2),
        "images": len(list(dataset.items())),
        "detections": len(detections),
        "postprocessor": "agrinav.inference.postprocess.decode_batch (class-aware)",
    }
    return result, detections, protocol


def summarize(result: CocoEvalResult, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten metrics plus protocol into one JSON-serializable report."""
    report: dict[str, Any] = {
        "ap": result.ap,
        "ap50": result.ap50,
        "ap75": result.ap75,
        "ap_small": result.ap_small,
        "ap_medium": result.ap_medium,
        "ap_large": result.ap_large,
        "ar_1": result.ar_1,
        "ar_10": result.ar_10,
        "ar_100": result.ar_100,
        "ar_small": result.ar_small,
        "ar_medium": result.ar_medium,
        "ar_large": result.ar_large,
        "per_category_ap": dict(result.per_category_ap),
        "category_names": dict(result.category_names),
        "num_images": result.num_images,
        "num_detections": result.num_detections,
        "num_gt_annotations": result.num_gt_annotations,
        "protocol": dict(protocol),
    }
    if not result.is_standard_maxdets:
        report["warning"] = (
            f"max_detections={result.max_dets} is not the COCO standard 100. "
            "pycocotools computes the primary AP at maxDets=100 only, so `ap` is "
            "the -1.0 sentinel here. Report this run separately; it is not "
            "comparable with a standard COCO AP."
        )
    return report


def _print_report(report: Mapping[str, Any]) -> None:
    protocol = report["protocol"]
    print(f"images={report['num_images']}  detections={report['num_detections']}  ")
    print(
        f"protocol: img={protocol['img_size']} score_thr={protocol['score_threshold']} "
        f"nms_iou={protocol['nms_iou']} max_dets={protocol['max_detections']} "
        f"soft_nms={protocol['use_soft_nms']}"
    )
    print(f"  AP@[.50:.95] {report['ap']:.4f}")
    print(f"  AP50         {report['ap50']:.4f}")
    print(f"  AP75         {report['ap75']:.4f}")
    print(f"  AP small     {report['ap_small']:.4f}")
    print(f"  AP medium    {report['ap_medium']:.4f}")
    print(f"  AP large     {report['ap_large']:.4f}")
    print(f"  AR@100       {report['ar_100']:.4f}")
    names = report["category_names"]
    for category_id, value in sorted(report["per_category_ap"].items()):
        print(f"  AP[{names.get(category_id, '?')}]  {value:.4f}")
    if "warning" in report:
        print(f"  WARNING: {report['warning']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agrinav evaluate-detector",
        description=(
            "Score a detector checkpoint on a split with pycocotools, using the "
            "canonical class-aware postprocessor."
        ),
    )
    parser.add_argument("--checkpoint", required=True, help="weeddet_*.pth to score")
    parser.add_argument("--ann-file", required=True, help="COCO ground truth for the split")
    parser.add_argument("--images-root", required=True, help="directory file_name resolves against")
    parser.add_argument(
        "--class-names",
        default=None,
        help="comma list; defaults to the class_names recorded in the checkpoint",
    )
    parser.add_argument("--img-size", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_EVAL_BATCH_SIZE)
    parser.add_argument("--device", default=None, help="cuda or cpu (default: cuda if available)")
    parser.add_argument("--score-threshold", type=float, default=DEFAULT_SCORE_THRESHOLD)
    parser.add_argument("--nms-iou", type=float, default=DEFAULT_NMS_IOU)
    parser.add_argument(
        "--max-detections",
        type=int,
        default=DEFAULT_MAX_DETECTIONS,
        help="COCO maxDets. Anything other than 100 is not a comparable COCO AP",
    )
    parser.add_argument("--hard-nms", action="store_true", help="hard NMS instead of Soft-NMS")
    parser.add_argument("--out", default=None, help="write the metrics report json here")
    parser.add_argument(
        "--save-detections", default=None, help="write raw COCO detections json here"
    )
    args = parser.parse_args(argv)

    from agrinav.training.weeddet_train import _CocoSplitDataset, load_checkpoint_model

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if args.device and args.device.startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit(
            f"--device {args.device!r} requested but CUDA is not available. Evaluation on "
            "CPU is valid but much slower -- pass --device cpu to accept that explicitly."
        )

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    names = args.class_names.split(",") if args.class_names else checkpoint.get("class_names")
    if not names:
        raise SystemExit(
            f"{args.checkpoint!r} records no class_names; pass --class-names explicitly "
            "(they must match what the checkpoint was trained with)."
        )
    class_names = tuple(name.strip() for name in names if str(name).strip())

    model = load_checkpoint_model(args.checkpoint, num_classes=len(class_names), device=device)
    dataset = _CocoSplitDataset(
        args.ann_file, args.images_root, class_names, img_size=args.img_size, augment=False
    )

    result, detections, protocol = evaluate_split(
        model,
        dataset,
        args.ann_file,
        device=device,
        img_size=args.img_size,
        batch_size=args.batch_size,
        score_threshold=args.score_threshold,
        nms_iou=args.nms_iou,
        max_detections=args.max_detections,
        use_soft_nms=not args.hard_nms,
        progress=True,
    )
    report = summarize(result, protocol)
    report["checkpoint"] = os.path.abspath(args.checkpoint)
    report["ann_file"] = os.path.abspath(args.ann_file)
    report["class_names"] = list(class_names)
    _print_report(report)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
        print(f"\nreport -> {args.out}")
    if args.save_detections:
        os.makedirs(os.path.dirname(os.path.abspath(args.save_detections)) or ".", exist_ok=True)
        with open(args.save_detections, "w", encoding="utf-8") as handle:
            json.dump(detections, handle)
        print(f"detections -> {args.save_detections}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
