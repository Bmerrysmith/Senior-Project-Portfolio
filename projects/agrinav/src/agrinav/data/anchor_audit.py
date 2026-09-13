#!/usr/bin/env python3
"""Measure how well the WeedDet anchor set can cover a split's ground-truth boxes.

Model-free and image-free: it needs only a COCO split JSON, because the
letterbox transform is a pure function of ``(image_width, image_height,
img_size)`` and the anchor shapes are a pure function of the anchor config.
That makes this the cheapest available check on a question no amount of
training can answer -- whether the detector's recall is capped by geometry.

WeedDet's :class:`~agrinav.models.weeddet_v6b.AnchorGenerator` uses aspect
ratios ``(0.2, 0.33, 0.5, 1.0)``: every anchor is square or *tall*, none is
wide. With ``base_scale=3`` and strides ``(4, 8, 16)`` the square anchors top
out at ``3 * 16 * 2**(2/3) ~= 76 px`` while the tallest reaches ~170 px in
height on a 512 px input. A ground-truth box that no anchor can reach at the
assigner's IoU threshold can never be matched to a positive anchor, so it
contributes no positive training signal and is effectively invisible to the
detector.

Two IoU numbers are reported per box:

``shape_iou``
    The upper bound: anchor and box share a centre, so only the width/height
    mismatch costs IoU. Unreachable regardless of where the box sits.
``grid_iou``
    The realisable value: anchor centres lie on a ``stride`` grid at
    ``(i + 0.5) * stride``, so the centre can be off by up to ``stride / 2`` per
    axis. Always <= ``shape_iou``.

A large low-``shape_iou`` tail is an architecture finding (fix the anchors); a
gap between the two is a stride/resolution finding.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from typing import Any, Iterable, Sequence

# Defaults mirror WeedDet's AnchorGenerator and the phase-2 detector config.
DEFAULT_ASPECT_RATIOS: tuple[float, ...] = (0.2, 0.33, 0.5, 1.0)
DEFAULT_SCALES: tuple[float, ...] = (1.0, 2 ** (1 / 3), 2 ** (2 / 3))
DEFAULT_STRIDES: tuple[int, ...] = (4, 8, 16)
DEFAULT_BASE_SCALE: int = 3
DEFAULT_IMG_SIZE: int = 512

# Reported coverage cut-offs. 0.5 is the common positive-assignment threshold;
# the lower ones show how deep the unreachable tail goes.
IOU_THRESHOLDS: tuple[float, ...] = (0.5, 0.4, 0.3)


def anchor_shapes(
    base_scale: int = DEFAULT_BASE_SCALE,
    aspect_ratios: Sequence[float] = DEFAULT_ASPECT_RATIOS,
    scales: Sequence[float] = DEFAULT_SCALES,
    strides: Sequence[int] = DEFAULT_STRIDES,
) -> list[tuple[float, float, int]]:
    """Return every distinct ``(width, height, stride)`` anchor shape.

    Mirrors ``AnchorGenerator._make_anchors``: ``w = base * scale * sqrt(ar)``
    and ``h = base * scale / sqrt(ar)`` with ``base = base_scale * stride``.
    """
    shapes: list[tuple[float, float, int]] = []
    for stride in strides:
        base = base_scale * stride
        for ratio in aspect_ratios:
            for scale in scales:
                width = base * scale * math.sqrt(ratio)
                height = base * scale / math.sqrt(ratio)
                shapes.append((width, height, stride))
    return shapes


def letterbox_params(
    image_w: int, image_h: int, img_size: int = DEFAULT_IMG_SIZE
) -> tuple[float, float, int, int]:
    """Replicate ``letterbox_pil``'s exact per-axis scales and padding.

    The integer resize means the realised x and y scales differ slightly from
    the nominal ``img_size / max(w, h)``; reproducing that here keeps the audit
    aligned with what the dataset actually feeds the model (audit fix P1-8).
    """
    nominal = img_size / max(image_w, image_h)
    new_w = max(int(image_w * nominal), 1)
    new_h = max(int(image_h * nominal), 1)
    return new_w / image_w, new_h / image_h, (img_size - new_w) // 2, (img_size - new_h) // 2


def _centred_iou(box_w: float, box_h: float, anc_w: float, anc_h: float) -> float:
    """IoU of two concentric axis-aligned boxes -- the achievable upper bound."""
    inter = min(box_w, anc_w) * min(box_h, anc_h)
    union = box_w * box_h + anc_w * anc_h - inter
    return inter / union if union > 0 else 0.0


def _grid_iou(
    cx: float,
    cy: float,
    box_w: float,
    box_h: float,
    anc_w: float,
    anc_h: float,
    stride: int,
) -> float:
    """IoU against the nearest anchor of this shape on the stride grid.

    Anchor centres sit at ``(i + 0.5) * stride``. IoU falls monotonically with
    centre distance, so the nearest grid centre is the best one and no search
    is needed.
    """
    grid_cx = (math.floor(cx / stride) + 0.5) * stride
    grid_cy = (math.floor(cy / stride) + 0.5) * stride
    inter_w = max(
        0.0, min(cx + box_w / 2, grid_cx + anc_w / 2) - max(cx - box_w / 2, grid_cx - anc_w / 2)
    )
    inter_h = max(
        0.0, min(cy + box_h / 2, grid_cy + anc_h / 2) - max(cy - box_h / 2, grid_cy - anc_h / 2)
    )
    inter = inter_w * inter_h
    union = box_w * box_h + anc_w * anc_h - inter
    return inter / union if union > 0 else 0.0


def best_iou_for_box(
    cx: float,
    cy: float,
    box_w: float,
    box_h: float,
    shapes: Sequence[tuple[float, float, int]],
) -> tuple[float, float]:
    """Return ``(best_shape_iou, best_grid_iou)`` over every anchor shape."""
    best_shape = best_grid = 0.0
    for anc_w, anc_h, stride in shapes:
        best_shape = max(best_shape, _centred_iou(box_w, box_h, anc_w, anc_h))
        best_grid = max(best_grid, _grid_iou(cx, cy, box_w, box_h, anc_w, anc_h, stride))
    return best_shape, best_grid


def _size_bucket(area: float) -> str:
    """COCO's small/medium/large split, in letterboxed pixels."""
    if area < 32 * 32:
        return "small"
    if area < 96 * 96:
        return "medium"
    return "large"


def _ratio_bucket(width: float, height: float) -> str:
    """Wide boxes are the ones the tall-only anchor set cannot represent."""
    ratio = width / height if height > 0 else float("inf")
    if ratio >= 2.0:
        return "wide(w/h>=2)"
    if ratio >= 1.2:
        return "slightly_wide(1.2-2)"
    if ratio >= 0.8:
        return "square(0.8-1.2)"
    return "tall(w/h<0.8)"


def iter_gt_boxes(coco: dict[str, Any], img_size: int) -> Iterable[dict[str, Any]]:
    """Yield each annotation mapped into letterboxed network coordinates.

    Applies the same ``w > 1 and h > 1`` pre-filter and post-letterbox
    ``>= 1 px`` filter as ``CocoWeedDataset.__getitem__``, so the audited set is
    the set the model actually trains on.
    """
    images = {im["id"]: im for im in coco["images"]}
    names = {c["id"]: c["name"] for c in coco.get("categories", [])}
    for ann in coco.get("annotations", []):
        image = images.get(ann["image_id"])
        if image is None:
            continue
        x, y, w, h = ann["bbox"]
        if w <= 1 or h <= 1:
            continue
        sx, sy, pad_l, pad_t = letterbox_params(image["width"], image["height"], img_size)
        x0 = min(max(x * sx + pad_l, 0.0), img_size)
        x1 = min(max((x + w) * sx + pad_l, 0.0), img_size)
        y0 = min(max(y * sy + pad_t, 0.0), img_size)
        y1 = min(max((y + h) * sy + pad_t, 0.0), img_size)
        box_w, box_h = x1 - x0, y1 - y0
        if box_w < 1 or box_h < 1:
            continue
        yield {
            "class_name": names.get(ann["category_id"], str(ann["category_id"])),
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "w": box_w,
            "h": box_h,
        }


def audit(
    ann_file: str | os.PathLike[str],
    img_size: int = DEFAULT_IMG_SIZE,
    base_scale: int = DEFAULT_BASE_SCALE,
    aspect_ratios: Sequence[float] = DEFAULT_ASPECT_RATIOS,
    strides: Sequence[int] = DEFAULT_STRIDES,
) -> dict[str, Any]:
    """Compute anchor-coverage statistics for one COCO split."""
    with open(ann_file, encoding="utf-8") as handle:
        coco = json.load(handle)

    shapes = anchor_shapes(base_scale, aspect_ratios, DEFAULT_SCALES, strides)
    totals = {"n_boxes": 0}
    # Seeded with every key so "nothing was below this threshold" reports as an
    # explicit 0.0 rather than a missing key the caller has to guess about.
    below: dict[str, int] = defaultdict(int)
    for threshold in IOU_THRESHOLDS:
        below[f"grid_iou<{threshold}"] = 0
        below[f"shape_iou<{threshold}"] = 0
    by_group: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    shape_ious: list[float] = []
    grid_ious: list[float] = []

    for box in iter_gt_boxes(coco, img_size):
        shape_iou, grid_iou = best_iou_for_box(box["cx"], box["cy"], box["w"], box["h"], shapes)
        totals["n_boxes"] += 1
        shape_ious.append(shape_iou)
        grid_ious.append(grid_iou)
        groups = (
            f"class:{box['class_name']}",
            f"size:{_size_bucket(box['w'] * box['h'])}",
            f"ratio:{_ratio_bucket(box['w'], box['h'])}",
        )
        for group in groups:
            by_group[group]["n"] += 1
        for threshold in IOU_THRESHOLDS:
            if grid_iou < threshold:
                below[f"grid_iou<{threshold}"] += 1
                for group in groups:
                    by_group[group][f"below_{threshold}"] += 1
            if shape_iou < threshold:
                below[f"shape_iou<{threshold}"] += 1

    n = max(totals["n_boxes"], 1)
    return {
        "ann_file": os.fspath(ann_file),
        "img_size": img_size,
        "anchor_config": {
            "base_scale": base_scale,
            "aspect_ratios": list(aspect_ratios),
            "scales": list(DEFAULT_SCALES),
            "strides": list(strides),
            "n_distinct_shapes": len(shapes),
            "min_side_px": round(min(min(w, h) for w, h, _ in shapes), 2),
            "max_side_px": round(max(max(w, h) for w, h, _ in shapes), 2),
            "max_aspect_ratio_w_over_h": round(max(w / h for w, h, _ in shapes), 3),
        },
        "n_boxes": totals["n_boxes"],
        "mean_shape_iou": round(sum(shape_ious) / n, 4),
        "mean_grid_iou": round(sum(grid_ious) / n, 4),
        "fractions": {key: round(count / n, 4) for key, count in sorted(below.items())},
        "counts": dict(sorted(below.items())),
        "by_group": {
            group: {
                "n": stats["n"],
                **{
                    f"frac_grid_iou<{t}": round(stats.get(f"below_{t}", 0) / max(stats["n"], 1), 4)
                    for t in IOU_THRESHOLDS
                },
            }
            for group, stats in sorted(by_group.items())
        },
    }


def _print_report(report: dict[str, Any]) -> None:
    cfg = report["anchor_config"]
    print(f"anchor audit: {report['ann_file']}")
    print(f"  img_size={report['img_size']}  boxes={report['n_boxes']}")
    print(
        f"  anchors: {cfg['n_distinct_shapes']} shapes, sides "
        f"{cfg['min_side_px']}-{cfg['max_side_px']} px, "
        f"max w/h={cfg['max_aspect_ratio_w_over_h']}"
    )
    print(f"  mean best IoU: shape={report['mean_shape_iou']} grid={report['mean_grid_iou']}")
    print("  uncovered fractions:")
    for key, value in report["fractions"].items():
        print(f"    {key:<18} {value:>7.2%}")
    print("  by group (grid IoU):")
    for group, stats in report["by_group"].items():
        cells = "  ".join(f"<{t}:{stats[f'frac_grid_iou<{t}']:.2%}" for t in IOU_THRESHOLDS)
        print(f"    {group:<34} n={stats['n']:<7} {cells}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agrinav data-anchor-audit",
        description=(
            "Model-free check of whether the WeedDet anchor set can cover a split's "
            "ground-truth boxes. Needs only the COCO json -- no images, no GPU."
        ),
    )
    parser.add_argument("--ann-file", required=True, help="COCO split json to audit")
    parser.add_argument(
        "--img-size", type=int, default=DEFAULT_IMG_SIZE, help="letterbox size (default: 512)"
    )
    parser.add_argument(
        "--base-scale", type=int, default=DEFAULT_BASE_SCALE, help="anchor base scale (default: 3)"
    )
    parser.add_argument(
        "--aspect-ratios",
        default=",".join(str(r) for r in DEFAULT_ASPECT_RATIOS),
        help="comma list of anchor aspect ratios (w/h); try adding wide ratios to "
        "see how much of the uncovered tail they would recover",
    )
    parser.add_argument(
        "--strides",
        default=",".join(str(s) for s in DEFAULT_STRIDES),
        help="comma list of feature strides (default: 4,8,16)",
    )
    parser.add_argument("--out", default=None, help="write the full report as json here")
    args = parser.parse_args(argv)

    report = audit(
        args.ann_file,
        img_size=args.img_size,
        base_scale=args.base_scale,
        aspect_ratios=tuple(float(r) for r in args.aspect_ratios.split(",") if r.strip()),
        strides=tuple(int(s) for s in args.strides.split(",") if s.strip()),
    )
    _print_report(report)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
        print(f"\nreport -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
