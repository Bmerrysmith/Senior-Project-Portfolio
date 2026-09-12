#!/usr/bin/env python3
"""Reviewed annotation records -> an Ultralytics YOLOv8/v11 dataset.

WHERE THIS SITS IN THE PIPELINE
-------------------------------
This is the *back door* of the automated annotation pipeline
(``docs/annotation_guide.md`` §8)::

    scripts/locateanything_to_proposals.py  boxes  -> COCO proposals
    scripts/sam_box_to_mask.py              boxes  -> SAM masks
    scripts/triage_proposals.py             route to human review
    <<< HUMAN REVIEW mints ground truth >>>
    (this script)   accepted records -> images/ + labels/ + data.yaml

Input is the per-image JSONL described by
``data/schemas/annotation_record.v1.schema.json`` and enforced by
``scripts/validate_annotation_package.py``. Output is a standard Ultralytics
dataset (``images/{train,val,test}``, ``labels/{...}/*.txt``, ``data.yaml``)
for ``segment`` (polygons) or ``detect`` (boxes).

WHY THE DEFAULT IS TRUTH-ONLY
-----------------------------
The forbidden inference ``proposal => accepted ground truth``
(``data/ontology.v1.json``) is the whole reason this project keeps a proposal
layer separate from truth. So:

* By default this exporter emits ONLY canonical truth: records whose
  ``review.review_status`` is ``accepted`` or ``adjudicated``, that are not
  ``unusable``, and per-object annotations whose ``human_edit_action`` is not
  ``deleted``. Everything else is a *counted* skip.
* ``--include-unreviewed`` is a research-only escape hatch for a bootstrapping
  loop. It writes to the same tree but stamps ``UNREVIEWED_DO_NOT_TRAIN.txt``
  and records the weakened gate in ``data.yaml`` and ``export_report.json``.
  Unusable / ``rejected_unusable`` images are dropped even then.
* Labels are read through a **closed** class map (``--classes``). A label not
  in the map is a counted drop, never coerced to a neighbouring class.
* The split comes from the immutable ``source.split``; a record is never moved
  between splits, so the sealed test set stays sealed. ``unassigned`` is never
  placed into ``train``.

No heavy deps at import. Polygon export is pure-Python; RLE masks need
``pycocotools``/``opencv`` and degrade to a counted skip when absent.

Usage::

    python -m agrinav.data.export_yolo_dataset \
        --packages artifacts/annotation/reviewed/*.jsonl \
        --images-root ~/agrinav_data/derived/images \
        --out-root artifacts/yolo/weeddet_v1 \
        --task segment --classes rice_protect,weed_target

Contract check (no images, no cv2)::

    python -m agrinav.data.export_yolo_dataset --self-test
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

ACCEPTED_REVIEW_STATES = frozenset({"accepted", "adjudicated"})

# source.split -> YOLO split dir. Ultralytics conventionally calls it "val".
DEFAULT_SPLIT_DIRS: dict[str, str] = {
    "train": "train",
    "validation": "val",
    "test": "test",
}

DEFAULT_CLASSES = (
    "rice_protect",
    "weed_target",
    "unknown_vegetation",
    "non_target_aquatic",
    "ground_exclusion",
)


class ExportError(RuntimeError):
    """Fatal preflight/contract failure."""


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------


def bbox_from_polygon(polygon: Sequence[float]) -> tuple[float, float, float, float]:
    xs = [float(v) for v in polygon[0::2]]
    ys = [float(v) for v in polygon[1::2]]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return x0, y0, x1 - x0, y1 - y0


def decode_rle_to_mask(size: Sequence[int], counts: Any):
    """Decode a COCO RLE (compressed str or uncompressed run list) -> bool mask.

    Returns an ``np.ndarray`` of shape (h, w) or raises ``ExportError`` when the
    needed optional dependency is missing. Never fabricates geometry.
    """
    import numpy as np

    height, width = int(size[0]), int(size[1])
    if isinstance(counts, str):
        try:
            from pycocotools import mask as coco_mask  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dep
            raise ExportError(
                "compressed RLE counts need pycocotools; install it or export " "polygon geometry"
            ) from exc
        decoded = coco_mask.decode({"size": [height, width], "counts": counts.encode("ascii")})
        return decoded.astype(bool)
    # Uncompressed COCO run-length: column-major (Fortran), starts with a 0-run.
    flat = np.zeros(height * width, dtype=bool)
    idx = 0
    value = False
    for run in counts:
        run = int(run)
        flat[idx : idx + run] = value
        idx += run
        value = not value
    return flat.reshape((height, width), order="F")


def bbox_from_mask(mask) -> tuple[float, float, float, float] | None:
    import numpy as np

    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        return None
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    return x0, y0, (x1 - x0 + 1.0), (y1 - y0 + 1.0)


def mask_to_polygon(mask) -> list[float] | None:
    """Largest external contour of a mask as a flat polygon. Needs opencv."""
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise ExportError(
            "RLE->polygon for segment export needs opencv-python; install it or "
            "export polygon geometry directly"
        ) from exc
    import numpy as np

    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    if biggest.shape[0] < 3:
        return None
    eps = 0.005 * cv2.arcLength(biggest, True)
    approx = cv2.approxPolyDP(biggest, eps, True)
    pts = approx.reshape(-1, 2)
    if pts.shape[0] < 3:
        pts = biggest.reshape(-1, 2)
    return [float(v) for v in pts.reshape(-1)]


def _norm_clip(value: float, size: int) -> float:
    return min(1.0, max(0.0, value / float(size)))


def detect_line(cls: int, bbox_xywh: Sequence[float], width: int, height: int) -> str | None:
    x, y, w, h = (float(v) for v in bbox_xywh)
    if w <= 0 or h <= 0:
        return None
    cx = _norm_clip(x + w / 2.0, width)
    cy = _norm_clip(y + h / 2.0, height)
    nw = _norm_clip(w, width)
    nh = _norm_clip(h, height)
    if nw <= 0 or nh <= 0:
        return None
    return f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def segment_line(cls: int, polygon: Sequence[float], width: int, height: int) -> str | None:
    if len(polygon) < 6:
        return None
    coords: list[str] = []
    for i in range(0, len(polygon) - 1, 2):
        nx = _norm_clip(float(polygon[i]), width)
        ny = _norm_clip(float(polygon[i + 1]), height)
        coords.append(f"{nx:.6f}")
        coords.append(f"{ny:.6f}")
    if len(coords) < 6:
        return None
    return f"{cls} " + " ".join(coords)


# --------------------------------------------------------------------------
# per-record -> label lines
# --------------------------------------------------------------------------


def annotation_to_line(
    ann: dict[str, Any],
    *,
    cls: int,
    task: str,
    width: int,
    height: int,
    drops: dict[str, int],
) -> str | None:
    geom = ann.get("geometry") or {}
    gtype = geom.get("type")
    if task == "detect":
        if gtype == "bbox":
            bbox = geom["bbox"]
        elif gtype == "polygon":
            bbox = bbox_from_polygon(geom["polygon"])
        elif gtype in ("instance_mask", "semantic_mask"):
            try:
                mask = decode_rle_to_mask(geom["rle"]["size"], geom["rle"]["counts"])
            except ExportError:
                drops["rle_decode_unavailable"] = drops.get("rle_decode_unavailable", 0) + 1
                return None
            bbox = bbox_from_mask(mask)
            if bbox is None:
                drops["empty_mask"] = drops.get("empty_mask", 0) + 1
                return None
        else:
            drops[f"unknown_geometry={gtype!r}"] = drops.get(f"unknown_geometry={gtype!r}", 0) + 1
            return None
        line = detect_line(cls, bbox, width, height)
        if line is None:
            drops["degenerate_box"] = drops.get("degenerate_box", 0) + 1
        return line
    # segment
    if gtype == "polygon":
        line = segment_line(cls, geom["polygon"], width, height)
        if line is None:
            drops["degenerate_polygon"] = drops.get("degenerate_polygon", 0) + 1
        return line
    if gtype in ("instance_mask", "semantic_mask"):
        try:
            mask = decode_rle_to_mask(geom["rle"]["size"], geom["rle"]["counts"])
            polygon = mask_to_polygon(mask)
        except ExportError:
            drops["rle_polygon_unavailable"] = drops.get("rle_polygon_unavailable", 0) + 1
            return None
        if polygon is None:
            drops["empty_mask_polygon"] = drops.get("empty_mask_polygon", 0) + 1
            return None
        line = segment_line(cls, polygon, width, height)
        if line is None:
            drops["degenerate_polygon"] = drops.get("degenerate_polygon", 0) + 1
        return line
    # A box has no mask; do NOT fabricate one for a segmentation dataset.
    drops["bbox_only_in_segment_mode"] = drops.get("bbox_only_in_segment_mode", 0) + 1
    return None


def record_label_lines(
    record: dict[str, Any],
    *,
    class_index: dict[str, int],
    task: str,
    include_unreviewed: bool,
    drops: dict[str, int],
) -> tuple[list[str] | None, str | None]:
    """Return (label_lines, split_dir) for a record, or (None, None) to skip.

    An empty list of lines is a legitimate background/negative image; None is a
    skip. ``split_dir`` is None when skipped.
    """
    review = record.get("review") or {}
    status = review.get("review_status")
    unusable = bool(record.get("unusable", False))

    if unusable or status == "rejected_unusable":
        drops["unusable"] = drops.get("unusable", 0) + 1
        return None, None
    if not include_unreviewed and status not in ACCEPTED_REVIEW_STATES:
        drops[f"not_truth_review_status={status!r}"] = (
            drops.get(f"not_truth_review_status={status!r}", 0) + 1
        )
        return None, None

    source = record.get("source") or {}
    split = source.get("split")
    split_dir = DEFAULT_SPLIT_DIRS.get(split)
    if split_dir is None:
        drops[f"split_excluded={split!r}"] = drops.get(f"split_excluded={split!r}", 0) + 1
        return None, None

    width = source.get("width")
    height = source.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        drops["bad_image_dims"] = drops.get("bad_image_dims", 0) + 1
        return None, None

    lines: list[str] = []
    for ann in record.get("annotations", []):
        attrs = ann.get("attributes") or {}
        if attrs.get("human_edit_action") == "deleted":
            drops["deleted_object"] = drops.get("deleted_object", 0) + 1
            continue
        label = ann.get("label")
        cls = class_index.get(label)
        if cls is None:
            drops[f"label_not_in_class_map={label!r}"] = (
                drops.get(f"label_not_in_class_map={label!r}", 0) + 1
            )
            continue
        line = annotation_to_line(ann, cls=cls, task=task, width=width, height=height, drops=drops)
        if line is not None:
            lines.append(line)
    return lines, split_dir


# --------------------------------------------------------------------------
# image staging
# --------------------------------------------------------------------------


def resolve_image(images_root: Path | None, record: dict[str, Any]) -> Path | None:
    if images_root is None:
        return None
    source = record.get("source") or {}
    uri = source.get("image_uri") or record.get("image_id")
    if not isinstance(uri, str):
        return None
    candidates = [
        Path(uri),
        images_root / uri,
        images_root / Path(uri).name,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def stage_image(src: Path, dst: Path, link: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    if link == "copy":
        shutil.copy2(src, dst)
    elif link == "symlink":
        try:
            dst.symlink_to(src.resolve())
        except OSError:
            shutil.copy2(src, dst)  # Windows without privilege -> fall back
    else:  # "none"
        return


def label_stem(record: dict[str, Any], used: set[str]) -> str:
    source = record.get("source") or {}
    uri = source.get("image_uri") or record.get("image_id") or record.get("record_id") or "image"
    stem = Path(str(uri)).stem or "image"
    stem = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in stem)
    candidate = stem
    n = 1
    while candidate in used:
        n += 1
        candidate = f"{stem}__{n}"
    used.add(candidate)
    return candidate


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def iter_records(packages: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for pkg in packages:
        with pkg.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def export(
    *,
    packages: list[Path],
    out_root: Path,
    images_root: Path | None,
    task: str,
    classes: list[str],
    include_unreviewed: bool,
    link: str,
) -> dict[str, Any]:
    if task not in ("detect", "segment"):
        raise ExportError(f"--task must be 'detect' or 'segment', got {task!r}")
    if link not in ("copy", "symlink", "none"):
        raise ExportError(f"--link must be copy|symlink|none, got {link!r}")
    class_index = {name: i for i, name in enumerate(classes)}

    drops: dict[str, int] = {}
    used_stems: dict[str, set[str]] = {}
    per_split: dict[str, dict[str, int]] = {}
    image_lists: dict[str, list[str]] = {}
    missing_images = 0

    for record in iter_records(packages):
        lines, split_dir = record_label_lines(
            record,
            class_index=class_index,
            task=task,
            include_unreviewed=include_unreviewed,
            drops=drops,
        )
        if split_dir is None:
            continue
        used = used_stems.setdefault(split_dir, set())
        stem = label_stem(record, used)

        # image
        src = resolve_image(images_root, record)
        img_rel: str | None = None
        if src is not None:
            img_dst = out_root / "images" / split_dir / f"{stem}{src.suffix.lower()}"
            stage_image(src, img_dst, link)
            img_rel = f"images/{split_dir}/{img_dst.name}"
        else:
            if link != "none":
                missing_images += 1
            # Even with no file, record the expected path so the list is usable.
            source = record.get("source") or {}
            uri = source.get("image_uri") or record.get("image_id") or stem
            img_rel = f"images/{split_dir}/{Path(str(uri)).name}"

        # label (empty file = background/negative, which YOLO wants)
        label_dst = out_root / "labels" / split_dir / f"{stem}.txt"
        label_dst.parent.mkdir(parents=True, exist_ok=True)
        label_dst.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

        image_lists.setdefault(split_dir, []).append(img_rel)
        bucket = per_split.setdefault(split_dir, {"images": 0, "objects": 0, "empty_images": 0})
        bucket["images"] += 1
        bucket["objects"] += len(lines)
        if not lines:
            bucket["empty_images"] += 1

    # data.yaml
    gating = "UNREVIEWED_INCLUDED_research_only" if include_unreviewed else "truth_only"
    yaml_lines = [
        "# Generated by scripts/export_yolo_dataset.py",
        "# Model output is a proposal until human review is accepted.",
        f"# gating: {gating}",
        f"# task: {task}",
        f"path: {out_root.resolve().as_posix()}",
    ]
    for split in ("train", "val", "test"):
        if split in per_split:
            yaml_lines.append(f"{split}: images/{split}")
    yaml_lines.append("names:")
    for i, name in enumerate(classes):
        yaml_lines.append(f"  {i}: {name}")
    (out_root).mkdir(parents=True, exist_ok=True)
    (out_root / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    # image list files (handy for link=none staging)
    for split_dir, items in image_lists.items():
        (out_root / f"{split_dir}_images.txt").write_text("\n".join(items) + "\n", encoding="utf-8")

    if include_unreviewed:
        (out_root / "UNREVIEWED_DO_NOT_TRAIN.txt").write_text(
            "This export includes UNREVIEWED proposals (--include-unreviewed).\n"
            "Model output is not ground truth. Do NOT use this as a truth set for\n"
            "safety-relevant claims. Re-export with review gating for training.\n",
            encoding="utf-8",
        )

    report = {
        "task": task,
        "gating": gating,
        "classes": classes,
        "packages": [str(p) for p in packages],
        "per_split": per_split,
        "drops": drops,
        "missing_images": missing_images,
        "link": link,
    }
    (out_root / "export_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def _record(
    *,
    record_id: str,
    split: str,
    status: str,
    annotations: list[dict[str, Any]],
    unusable: bool = False,
    verified_empty: Any = None,
) -> dict[str, Any]:
    return {
        "schema_version": "agrinav.annotation_record.v1",
        "record_id": record_id,
        "image_id": f"{record_id}.png",
        "source": {
            "dataset_id": "selftest",
            "dataset_version": "1",
            "image_uri": f"{record_id}.png",
            "source_image_sha256": "0" * 64,
            "width": 100,
            "height": 100,
            "country": None,
            "site_id": None,
            "field_id": None,
            "session_id": None,
            "capture_pass_id": None,
            "frame_id": None,
            "source_photo_id": None,
            "group_id": record_id,
            "split": split,
            "capture_metadata": None,
        },
        "provenance": {
            "proposal_model_id": None,
            "proposal_model_revision": None,
            "proposal_method": "manual",
            "prompt": None,
            "thresholds": None,
            "generated_at": None,
            "original_proposal": None,
            "human_edit_state": "human_only",
        },
        "review": {
            "annotator_id": "a",
            "annotator_completed_at": None,
            "reviewer_id": "r",
            "reviewed_at": None,
            "review_status": status,
            "annotation_version": "1",
            "guide_version": "1",
        },
        "verified_empty": verified_empty,
        "unusable": unusable,
        "annotations": annotations,
    }


def _obj(label: str, geometry: dict[str, Any], edit: str | None = "accepted") -> dict[str, Any]:
    return {
        "annotation_id": f"o-{label}",
        "label": label,
        "biological_class": "weed" if label == "weed_target" else "rice",
        "decision_role": "target" if label == "weed_target" else "protect",
        "geometry": geometry,
        "attributes": {
            "source_object_id": None,
            "species": None,
            "growth_stage": None,
            "occlusion": "none",
            "truncated": False,
            "annotation_confidence": "certain",
            "treatment_eligible": None,
            "human_edit_action": edit,
        },
    }


def _self_test() -> int:
    import tempfile

    poly = {"type": "polygon", "polygon": [10, 10, 30, 10, 30, 30, 10, 30]}
    box = {"type": "bbox", "bbox": [40, 40, 20, 20]}
    rle = {"type": "instance_mask", "rle": {"size": [100, 100], "counts": _rle_counts_square()}}

    records = [
        # accepted train: rice polygon + weed box + a DELETED weed (must drop)
        _record(
            record_id="t1",
            split="train",
            status="accepted",
            annotations=[
                _obj("rice_protect", poly),
                _obj("weed_target", box),
                _obj("weed_target", box, edit="deleted"),
            ],
        ),
        # adjudicated validation: weed via RLE mask (detect must decode; segment needs cv2)
        _record(
            record_id="v1",
            split="validation",
            status="adjudicated",
            annotations=[
                _obj("weed_target", rle),
            ],
        ),
        # sealed test, accepted, verified empty -> empty label (negative)
        _record(
            record_id="s1", split="test", status="accepted", annotations=[], verified_empty=True
        ),
        # UNREVIEWED proposal -> must be skipped by default
        _record(
            record_id="p1",
            split="train",
            status="unreviewed",
            annotations=[
                _obj("weed_target", box),
            ],
        ),
        # unusable -> always skipped
        _record(record_id="u1", split="train", status="in_review", annotations=[], unusable=True),
        # unassigned split -> excluded (never dumped into train)
        _record(
            record_id="x1",
            split="unassigned",
            status="accepted",
            annotations=[
                _obj("weed_target", box),
            ],
        ),
        # a label outside a reduced class map -> counted drop (tested below)
        _record(
            record_id="t2",
            split="train",
            status="accepted",
            annotations=[
                _obj("rice_protect", poly),
            ],
        ),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pkg = tmp / "reviewed.jsonl"
        pkg.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

        # DETECT export, full class map, no images (link=none).
        out_det = tmp / "yolo_detect"
        rep = export(
            packages=[pkg],
            out_root=out_det,
            images_root=None,
            task="detect",
            classes=list(DEFAULT_CLASSES),
            include_unreviewed=False,
            link="none",
        )
        assert rep["gating"] == "truth_only", rep
        # train: t1 (rice+weed, deleted dropped) + t2 (rice) = 2 images, 3 objects
        assert rep["per_split"]["train"]["images"] == 2, rep["per_split"]
        assert rep["per_split"]["train"]["objects"] == 3, rep["per_split"]
        # val: v1 RLE weed decoded to a box = 1 object
        assert rep["per_split"]["val"]["objects"] == 1, rep["per_split"]
        # test: s1 verified-empty negative = 1 image, 0 objects, 1 empty
        assert rep["per_split"]["test"] == {"images": 1, "objects": 0, "empty_images": 1}, rep[
            "per_split"
        ]
        assert rep["drops"].get("deleted_object") == 1, rep["drops"]
        assert any(k.startswith("not_truth_review_status=") for k in rep["drops"]), rep["drops"]
        assert rep["drops"].get("unusable") == 1, rep["drops"]
        assert rep["drops"].get("split_excluded='unassigned'") == 1, rep["drops"]
        # data.yaml + label content sanity
        yaml_text = (out_det / "data.yaml").read_text(encoding="utf-8")
        assert "task: detect" in yaml_text and "0: rice_protect" in yaml_text
        t1_label = (
            (out_det / "labels" / "train" / "t1.txt")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        assert len(t1_label) == 2 and all(len(line.split()) == 5 for line in t1_label), t1_label
        s1_label = (out_det / "labels" / "test" / "s1.txt").read_text(encoding="utf-8")
        assert s1_label == "", repr(s1_label)  # empty negative

        # SEGMENT export with a REDUCED class map (weed+rice only). The RLE mask
        # in v1 needs opencv; degrade to a counted skip if unavailable.
        out_seg = tmp / "yolo_seg"
        rep2 = export(
            packages=[pkg],
            out_root=out_seg,
            images_root=None,
            task="segment",
            classes=["rice_protect", "weed_target"],
            include_unreviewed=False,
            link="none",
        )
        # weed box in t1 has no mask -> must be a counted skip, not a fake polygon
        assert rep2["drops"].get("bbox_only_in_segment_mode", 0) >= 1, rep2["drops"]
        # rice polygon still exported
        t1_seg = (
            (out_seg / "labels" / "train" / "t1.txt")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        assert len(t1_seg) == 1 and t1_seg[0].startswith("0 "), t1_seg
        assert len(t1_seg[0].split()) >= 7, t1_seg  # cls + >=3 xy pairs

        # INCLUDE-UNREVIEWED escape hatch stamps the marker + weakens gate.
        out_un = tmp / "yolo_unrev"
        rep3 = export(
            packages=[pkg],
            out_root=out_un,
            images_root=None,
            task="detect",
            classes=list(DEFAULT_CLASSES),
            include_unreviewed=True,
            link="none",
        )
        assert rep3["gating"].startswith("UNREVIEWED"), rep3
        assert (out_un / "UNREVIEWED_DO_NOT_TRAIN.txt").is_file()
        # p1 (unreviewed) now included; u1 unusable still excluded
        assert rep3["per_split"]["train"]["images"] >= 3, rep3["per_split"]
        assert rep3["drops"].get("unusable") == 1, rep3["drops"]

    print("export_yolo_dataset self-test: OK")
    print("  detect per_split:", rep["per_split"])
    print("  detect drops:", rep["drops"])
    print("  segment drops:", rep2["drops"])
    return 0


def _rle_counts_square() -> list[int]:
    """Uncompressed COCO RLE (column-major) for a 20x20 square at (40,40) in 100x100."""
    height = width = 100
    x0 = y0 = 40
    side = 20
    flat = [0] * (height * width)  # column-major
    for col in range(x0, x0 + side):
        for row in range(y0, y0 + side):
            flat[col * height + row] = 1  # F-order index
    # run-length encode, starting with a 0-run
    counts: list[int] = []
    prev = 0
    run = 0
    for v in flat:
        if v == prev:
            run += 1
        else:
            counts.append(run)
            prev = v
            run = 1
    counts.append(run)
    return counts


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _expand_packages(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        matches = [Path(p) for p in glob.glob(pat)]
        out.extend(sorted(matches) if matches else [Path(pat)])
    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reviewed annotation records -> Ultralytics YOLOv8/v11 dataset"
    )
    ap.add_argument("--self-test", action="store_true", help="run the contract check and exit")
    ap.add_argument("--packages", nargs="+", help="JSONL annotation package(s); globs ok")
    ap.add_argument("--out-root", type=Path, help="output dataset root")
    ap.add_argument(
        "--images-root", type=Path, default=None, help="base dir to resolve source images"
    )
    ap.add_argument("--task", choices=["detect", "segment"], default="segment")
    ap.add_argument(
        "--classes",
        default=",".join(DEFAULT_CLASSES),
        help="comma list of ontology labels; index = position (closed map)",
    )
    ap.add_argument(
        "--include-unreviewed",
        action="store_true",
        help="RESEARCH ONLY: include unreviewed proposals; stamps a DO_NOT_TRAIN marker",
    )
    ap.add_argument("--link", choices=["copy", "symlink", "none"], default="copy")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.packages or args.out_root is None:
        ap.error("--packages and --out-root are required (or use --self-test)")

    classes = [c.strip() for c in args.classes.split(",") if c.strip()]
    unknown = [c for c in classes if c not in DEFAULT_CLASSES]
    if unknown:
        ap.error(f"--classes has non-ontology labels: {unknown} (valid: {list(DEFAULT_CLASSES)})")

    try:
        report = export(
            packages=_expand_packages(args.packages),
            out_root=args.out_root,
            images_root=args.images_root,
            task=args.task,
            classes=classes,
            include_unreviewed=args.include_unreviewed,
            link=args.link,
        )
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    banner = (
        "WROTE UNREVIEWED-INCLUSIVE dataset (research only — NOT training truth)"
        if args.include_unreviewed
        else "Wrote truth-only YOLO dataset"
    )
    print(f"{banner}: {args.out_root}")
    for key, value in report.items():
        print(f"  {key}: {value}")
    if report["missing_images"]:
        print(
            f"  warning: {report['missing_images']} image(s) not found under "
            f"--images-root; labels written, image files missing."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
