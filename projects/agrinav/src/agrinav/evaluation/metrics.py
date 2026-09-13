"""Standard COCO bounding-box AP for AgriNav detections.

Decode-agnostic by design (see the package docstring): this module scores
predictions that are already in COCO *detection* format against a COCO
ground-truth file. It never imports ``torch`` or the detector, so it is the one
piece of the evaluation stack that does **not** change when the canonical decode
(Gate-4 P1-6) lands.

Prediction format (one dict per detection)::

    {"image_id": int, "category_id": int, "bbox": [x, y, w, h], "score": float}

``bbox`` is top-left ``xywh`` in **original image pixel coordinates** — the same
space as the ground-truth boxes in the split JSON — and ``category_id`` is the
original COCO category id (e.g. one of ``{1, 2, 4}`` for this project), *not* the
detector's contiguous class index. Mapping the detector's output into this format
(inverse-letterbox + contiguous-id -> COCO-id) is the model-runner adapter's job
and is deliberately kept out of this module.

The primary metric is COCO ``AP@[.50:.95]`` at ``maxDets=100``. The July-20 audit
flags that a custom ``maxDets`` (e.g. 300) must not be reported under the standard
name; :class:`CocoEvalResult` records ``max_dets`` and ``is_standard_maxdets`` so a
non-standard run can never silently masquerade as the standard one.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
# Order matches pycocotools' COCOeval.stats[0:12] for bbox IoU.
_STAT_FIELDS = (
    "ap",  # AP @ [.50:.95] | area=all | maxDets=last
    "ap50",  # AP @ .50
    "ap75",  # AP @ .75
    "ap_small",
    "ap_medium",
    "ap_large",
    "ar_1",  # AR given 1 detection/image
    "ar_10",  # AR given 10 detections/image
    "ar_100",  # AR given maxDets detections/image (100 by default)
    "ar_small",
    "ar_medium",
    "ar_large",
)

_STANDARD_MAX_DETS = 100


@dataclass(frozen=True)
class CocoEvalResult:
    """Standard COCO bbox metrics plus per-category AP and provenance flags."""

    ap: float
    ap50: float
    ap75: float
    ap_small: float
    ap_medium: float
    ap_large: float
    ar_1: float
    ar_10: float
    ar_100: float
    ar_small: float
    ar_medium: float
    ar_large: float
    per_category_ap: dict[int, float]
    max_dets: int
    num_images: int
    num_detections: int
    num_gt_annotations: int
    category_names: dict[int, str] = field(default_factory=dict)

    @property
    def is_standard_maxdets(self) -> bool:
        """True only when ``maxDets`` is the standard COCO value of 100."""
        return self.max_dets == _STANDARD_MAX_DETS

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form (adds the derived ``is_standard_maxdets`` flag)."""
        data = asdict(self)
        # asdict keeps int keys; JSON needs str keys for the per-category maps.
        data["per_category_ap"] = {str(k): v for k, v in self.per_category_ap.items()}
        data["category_names"] = {str(k): v for k, v in self.category_names.items()}
        data["is_standard_maxdets"] = self.is_standard_maxdets
        return data

    def summary(self) -> str:
        """Human-readable multi-line report."""
        lines = [
            f"COCO bbox eval  (maxDets={self.max_dets}"
            f"{'' if self.is_standard_maxdets else '  [NON-STANDARD]'})",
            f"  images={self.num_images}  detections={self.num_detections}  "
            f"gt_annotations={self.num_gt_annotations}",
            f"  AP@[.50:.95] = {self.ap:.4f}",
            f"  AP@.50       = {self.ap50:.4f}",
            f"  AP@.75       = {self.ap75:.4f}",
            f"  AP small/medium/large = "
            f"{self.ap_small:.4f} / {self.ap_medium:.4f} / {self.ap_large:.4f}",
            f"  AR 1/10/{self.max_dets} = "
            f"{self.ar_1:.4f} / {self.ar_10:.4f} / {self.ar_100:.4f}",
            "  per-category AP@[.50:.95]:",
        ]
        for cat_id, ap in sorted(self.per_category_ap.items()):
            name = self.category_names.get(cat_id, "")
            label = f"{cat_id} ({name})" if name else str(cat_id)
            lines.append(f"    {label:<28} {ap:.4f}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Input loading + validation
# --------------------------------------------------------------------------- #
def _load_gt_dict(gt: str | os.PathLike[str] | Mapping[str, Any]) -> dict[str, Any]:
    """Load a COCO ground-truth mapping from a path or accept an in-memory dict."""
    if isinstance(gt, Mapping):
        return dict(gt)
    path = os.fspath(gt)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"ground-truth COCO file not found: {path!r}")
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(
            f"ground-truth {path!r} must be a COCO JSON object, got {type(data).__name__}"
        )
    return data


def _fill_derivable_gt_fields(gt_dict: dict[str, Any]) -> dict[str, Any]:
    """Supply ``area`` and ``iscrowd`` where an export omitted them.

    ``COCOeval`` indexes both unconditionally and raises a bare
    ``KeyError: 'area'`` from deep inside ``evaluateImg`` when they are absent —
    a real and common failure with hand-built or converted splits, and one whose
    traceback says nothing about which file is at fault.

    Both fields are *derivable*, so filling them changes no score: ``area`` is
    the box area COCO would have stored, and ``iscrowd`` defaults to 0 in the
    format itself. Anything not derivable is still rejected elsewhere rather than
    guessed. Operates on a copy; the caller's mapping is untouched.
    """
    annotations = gt_dict.get("annotations")
    if not annotations:
        return gt_dict
    if all("area" in ann and "iscrowd" in ann for ann in annotations):
        return gt_dict

    patched = dict(gt_dict)
    filled = []
    for ann in annotations:
        record = dict(ann)
        if "area" not in record:
            bbox = record.get("bbox")
            if not bbox or len(bbox) != 4:
                raise ValueError(
                    f"ground-truth annotation {record.get('id')!r} has neither 'area' nor a "
                    "4-element 'bbox'; COCOeval cannot score it"
                )
            record["area"] = float(bbox[2]) * float(bbox[3])
        record.setdefault("iscrowd", 0)
        filled.append(record)
    patched["annotations"] = filled
    return patched


def _load_detections(
    detections: Sequence[Mapping[str, Any]] | str | os.PathLike[str],
) -> list[dict[str, Any]]:
    """Load a detection list from a path or accept an in-memory sequence."""
    if isinstance(detections, (str, os.PathLike)):
        path = os.fspath(detections)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"predictions file not found: {path!r}")
        with open(path, encoding="utf-8") as handle:
            detections = json.load(handle)
    if not isinstance(detections, Sequence) or isinstance(detections, (str, bytes)):
        raise ValueError("predictions must be a list of detection objects")
    return [dict(d) for d in detections]


def _validate_detections(
    detections: list[dict[str, Any]],
    gt_image_ids: set[int],
    gt_category_ids: set[int],
) -> None:
    """Fail loudly with an actionable message before handing off to pycocotools.

    pycocotools' own ``loadRes`` asserts with an opaque "Results do not
    correspond to current coco set" on a mismatched image/category id; catch it
    here with a message that names the offending value.
    """
    required = {"image_id", "category_id", "bbox", "score"}
    for i, det in enumerate(detections):
        missing = required - det.keys()
        if missing:
            raise ValueError(f"detection[{i}] missing key(s) {sorted(missing)}: {det!r}")
        bbox = det["bbox"]
        if not isinstance(bbox, Sequence) or len(bbox) != 4:
            raise ValueError(f"detection[{i}] bbox must be [x, y, w, h], got {bbox!r}")
        if det["image_id"] not in gt_image_ids:
            raise ValueError(
                f"detection[{i}] image_id={det['image_id']!r} is not in the ground-truth "
                "set; predictions must reference the same images as the GT split."
            )
        if det["category_id"] not in gt_category_ids:
            raise ValueError(
                f"detection[{i}] category_id={det['category_id']!r} is not a GT category "
                f"{sorted(gt_category_ids)}; map the detector's contiguous class index to "
                "the original COCO category id before evaluating."
            )


# --------------------------------------------------------------------------- #
# Core evaluation
# --------------------------------------------------------------------------- #
def evaluate_coco_detections(
    gt: str | os.PathLike[str] | Mapping[str, Any],
    detections: Sequence[Mapping[str, Any]] | str | os.PathLike[str],
    *,
    max_dets: int = _STANDARD_MAX_DETS,
    iou_type: str = "bbox",
) -> CocoEvalResult:
    """Compute standard COCO AP for ``detections`` against ``gt``.

    Args:
        gt: path to a COCO ground-truth JSON, or the already-loaded mapping.
        detections: path to a JSON list of COCO detection dicts, or the list.
        max_dets: detections-per-image cap for the primary AP/AR. Defaults to the
            standard COCO value of 100; any other value sets
            :attr:`CocoEvalResult.is_standard_maxdets` to ``False``.
        iou_type: passed through to ``COCOeval`` (``"bbox"`` here; ``"segm"`` is
            accepted for future mask evaluation).

    Returns:
        A :class:`CocoEvalResult`.

    Raises:
        ValueError: on a malformed detection, or an image/category id that is not
            in the ground truth.
    """
    if max_dets <= 0:
        raise ValueError(f"max_dets must be positive, got {max_dets}")

    # Imported lazily so importing this module never requires pycocotools until
    # an evaluation is actually run.
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    gt_dict = _load_gt_dict(gt)
    det_list = _load_detections(detections)

    gt_image_ids = {int(img["id"]) for img in gt_dict.get("images", [])}
    categories = {int(c["id"]): c.get("name", "") for c in gt_dict.get("categories", [])}
    gt_category_ids = set(categories)
    num_gt_annotations = len(gt_dict.get("annotations", []))

    _validate_detections(det_list, gt_image_ids, gt_category_ids)
    gt_dict = _fill_derivable_gt_fields(gt_dict)

    # pycocotools chatters to stdout on load/eval; keep it out of clean logs.
    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO()
        coco_gt.dataset = gt_dict
        coco_gt.createIndex()

        coco_dt = coco_gt.loadRes(det_list) if det_list else _empty_res(coco_gt, COCO)

        coco_eval = COCOeval(coco_gt, coco_dt, iouType=iou_type)
        coco_eval.params.maxDets = [1, 10, max_dets]
        coco_eval.params.imgIds = sorted(gt_image_ids)
        coco_eval.evaluate()
        coco_eval.accumulate()
        coco_eval.summarize()

    stats = {name: float(coco_eval.stats[i]) for i, name in enumerate(_STAT_FIELDS)}
    per_cat = _per_category_ap(coco_eval, sorted(gt_category_ids))

    return CocoEvalResult(
        per_category_ap=per_cat,
        max_dets=max_dets,
        num_images=len(gt_image_ids),
        num_detections=len(det_list),
        num_gt_annotations=num_gt_annotations,
        category_names={cid: categories[cid] for cid in per_cat},
        **stats,
    )


def _empty_res(coco_gt: Any, coco_cls: Any) -> Any:
    """A valid empty COCO detection set (``loadRes([])`` is not reliable across versions)."""
    dt = coco_cls()
    dt.dataset = {
        "images": list(coco_gt.dataset.get("images", [])),
        "categories": list(coco_gt.dataset.get("categories", [])),
        "annotations": [],
    }
    dt.createIndex()
    return dt


def _per_category_ap(coco_eval: Any, category_ids: list[int]) -> dict[int, float]:
    """Per-category AP@[.50:.95] from ``COCOeval.eval['precision']``.

    ``precision`` has shape ``[T, R, K, A, M]`` (IoU thresholds, recall points,
    categories, area ranges, maxDet settings). Per category we average the valid
    (``> -1``) precision over all IoU thresholds and recall points at
    ``area=all`` (index 0) and the last ``maxDets`` setting.
    """
    precision = coco_eval.eval["precision"]  # type: ignore[index]
    # COCOeval orders the K axis by params.catIds; it defaults to all GT cats.
    cat_axis = list(coco_eval.params.catIds)
    out: dict[int, float] = {}
    for cat_id in category_ids:
        try:
            k = cat_axis.index(cat_id)
        except ValueError:  # pragma: no cover - cat present in GT by construction
            out[cat_id] = float("nan")
            continue
        p = precision[:, :, k, 0, -1]
        valid = p[p > -1]
        out[cat_id] = float(valid.mean()) if valid.size else float("nan")
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agrinav evaluate",
        description=(
            "Compute standard COCO bbox AP for a predictions file against a COCO "
            "ground-truth split. Decode-agnostic: it scores whatever predictions "
            "you give it. NEVER point --gt at the sealed test split during "
            "development; use val until a final locked evaluation."
        ),
    )
    parser.add_argument(
        "--gt",
        required=True,
        help="COCO ground-truth JSON (e.g. artifacts/detector_v1/split_v1/val.coco.json)",
    )
    parser.add_argument(
        "--predictions",
        required=True,
        help="JSON list of COCO detection dicts {image_id, category_id, bbox, score}",
    )
    parser.add_argument(
        "--max-dets",
        type=int,
        default=_STANDARD_MAX_DETS,
        help="detections/image cap for the primary AP (standard COCO = 100)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="optional path to write the metrics as JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``agrinav evaluate``."""
    args = _build_parser().parse_args(argv)
    result = evaluate_coco_detections(args.gt, args.predictions, max_dets=args.max_dets)
    print(result.summary())
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, indent=2, sort_keys=True)
        print(f"[metrics] wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
