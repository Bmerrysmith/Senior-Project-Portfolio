#!/usr/bin/env python3
"""Rebuild the phase-2 curated-RICE detector dataset from the source deliverable.

Why this exists
---------------
``RICE_curated_phase2.zip`` (the archive two phase-2 runs trained on) is not a
materialization of the grouped split it ships with. It was built by taking the
*native* Roboflow split and deleting the folder named ``test/``; the bundled
``grouped_split.json`` was never applied. Verified filename-by-filename:

===================  ==================  ==================
intended split       exported as train   exported as valid
===================  ==================  ==================
train                1,261               351
valid                358                 115
**test**             **179**             **52**
===================  ==================  ==================

That is 940 of 2,316 physical files in the wrong split, 231 of 261 intended
sealed-test images trained on, and a further 233 intended train/valid images
missing from the archive entirely (they sat in the deleted ``test/`` folder).
The archive therefore cannot be repaired by re-sorting its own contents.

This module rebuilds from the complete source
(``.../deliverable/detection/RICE/``: 2,579 images across
``images/{train,valid,test}``, 81,204 human-reviewed boxes) and:

1. assigns every image by ``grouped_split.json`` rather than by folder;
2. normalizes EXIF orientation and strips the tag, so pixels and boxes agree
   (214 of the 2,579 source images carry orientation 8 and are 90 degrees rotated
   relative to their annotations; 189 of those were inside the bad archive,
   carrying 3,093 boxes of which 430 are weed);
3. sanitizes boundary/degenerate boxes by one documented rule and writes a
   rejection report instead of dropping them silently;
4. records SHA256 for every emitted image and every emitted JSON;
5. re-verifies the result from disk (:func:`preflight`) and fails on any
   membership, hash, dimension, or count mismatch.

What it deliberately does not do
--------------------------------
*Invent a fresh test split.* ``grouped_split.json`` records ``num_groups: 68``
and ``block_size: 40`` but **not** per-file group ids, so the original grouping
cannot be reproduced exactly from the manifest. :func:`derive_group_id` provides
a documented *re-derivation* for diagnostics, and every emitted record carries it
plus a ``trained_on_legacy`` flag.

Measured on the 2026-07-29 build, a replacement is neither buildable nor needed:
of the 781 never-trained-on images, 83 of the 89 groups they span also contain a
trained-on image, leaving 6 images in a fully clean group -- with zero weed
boxes. And no metric was ever computed on the manifest's test split, so it stays
valid for any model trained from scratch on this build; only the 2026-07-28
checkpoints, which trained on part of it, may never be scored against it. See
``TEST_SPLIT_STATUS.md`` in the output.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

SPLITS: tuple[str, ...] = ("train", "valid", "test")

# The ontology the phase-2 config expects. The source ``instances_*.coco.json``
# files already use these ids/names; the sibling ``original_roboflow_boxes/``
# files carry identical boxes under Roboflow's raw names plus a junk id-0
# supercategory, so we read the former.
CATEGORIES: tuple[dict[str, Any], ...] = (
    {"id": 1, "name": "rice_protect", "supercategory": "plant"},
    {"id": 2, "name": "weed_target", "supercategory": "plant"},
)

# Re-encode quality for the images whose orientation had to be applied. Only
# those are re-encoded; every other image is copied byte-for-byte.
REORIENT_JPEG_QUALITY = 95

# Frame block size used by the source grouping method, mirrored here so the
# re-derived group ids line up with it as closely as the manifest allows.
DEFAULT_BLOCK_SIZE = 40

# Roboflow filenames look like ``<stem>_jpg.rf.<hash>.jpg``; the stem usually
# ends in a frame number (``frame_000657``, ``1a_image (101)``, ``seedlingCol_04_0083``).
_ROBOFLOW_NAME = re.compile(r"^(?P<stem>.+?)_jpg\.rf\.[0-9A-Za-z]+\.(?P<ext>jpg|jpeg|png)$", re.I)
_TRAILING_NUMBER = re.compile(r"^(?P<family>.*?)(?P<num>\d+)\)?$")


class BuildError(RuntimeError):
    """Raised when the rebuild cannot be completed correctly.

    Always carries an actionable message: what disagreed, by how much, and which
    file to look at.
    """


@dataclass(frozen=True)
class SourceImage:
    """One image as found in the source deliverable, before normalization."""

    file_name: str
    native_split: str
    path: str
    coco_width: int
    coco_height: int
    source_sha256: str | None
    annotations: tuple[dict[str, Any], ...]


@dataclass
class EmittedImage:
    """One image as written to the output tree."""

    file_name: str
    split: str
    native_split: str
    group_id: str
    width: int
    height: int
    sha256: str
    bytes_written: int
    reoriented: bool
    source_sha256: str | None = None
    trained_on_legacy: bool | None = None


@dataclass
class BoxDecision:
    """Outcome of applying the sanitation rule to one annotation."""

    bbox: list[float] | None
    action: str
    detail: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Grouping
# --------------------------------------------------------------------------- #
def derive_group_id(file_name: str, block_size: int = DEFAULT_BLOCK_SIZE) -> str:
    """Re-derive a capture-family + frame-block group id from a Roboflow filename.

    ``grouped_split.json`` describes its method as "grouped by capture-series
    family, 40-frame contiguous blocks" but does not store the resulting group
    ids, so this reconstructs the same *shape* of key: the filename stem with its
    trailing frame number removed (the family), plus the block index
    ``frame // block_size``.

    This is a **re-derivation, not the original grouping.** Use it for planning a
    replacement split and for leakage diagnostics; do not present it as the
    provenance of the existing train/valid assignment.

    Args:
        file_name: Roboflow-style file name, e.g. ``frame_000657_jpg.rf.ab12.jpg``.
        block_size: contiguous frames per block.

    Returns:
        ``"<family>#<block>"``, or ``"<stem>#na"`` when no frame number is present.
    """
    match = _ROBOFLOW_NAME.match(file_name)
    stem = match.group("stem") if match else os.path.splitext(file_name)[0]
    numbered = _TRAILING_NUMBER.match(stem)
    if not numbered:
        return f"{stem}#na"
    family = numbered.group("family").rstrip("_- ")
    block = int(numbered.group("num")) // max(1, block_size)
    return f"{family}#{block}"


# --------------------------------------------------------------------------- #
# Box sanitation
# --------------------------------------------------------------------------- #
def sanitize_box(
    bbox: Sequence[float],
    width: int,
    height: int,
    *,
    min_side: float = 1.0,
    tolerance: float = 1.0,
) -> BoxDecision:
    """Apply the one documented box rule: clip small excursions, reject the rest.

    The same rule must be used for training inputs and for evaluation ground
    truth, which is why it lives here and returns its reasoning.

    ============================  ========
    condition                     action
    ============================  ========
    inside bounds, side >= 1 px   ``keep``
    excursion <= ``tolerance``    ``clip``
    excursion > ``tolerance``     ``reject`` (``out_of_bounds``)
    side < ``min_side`` after clip ``reject`` (``degenerate``)
    non-finite or non-positive     ``reject`` (``invalid``)
    ============================  ========

    Args:
        bbox: COCO ``[x, y, w, h]`` in pixels.
        width: image width in pixels.
        height: image height in pixels.
        min_side: smallest width/height a surviving box may have.
        tolerance: how far outside the image a box may reach and still be clipped
            rather than rejected. 1 px absorbs off-by-one exports.

    Returns:
        A :class:`BoxDecision`; ``bbox`` is ``None`` for every ``reject``.
    """
    try:
        x, y, w, h = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return BoxDecision(None, "reject", {"reason": "invalid", "bbox": list(bbox)})
    if not all(map(_finite, (x, y, w, h))):
        return BoxDecision(None, "reject", {"reason": "invalid", "bbox": [x, y, w, h]})
    if w <= 0 or h <= 0:
        return BoxDecision(None, "reject", {"reason": "invalid", "bbox": [x, y, w, h]})

    x1, y1, x2, y2 = x, y, x + w, y + h
    excursion = max(-x1, -y1, x2 - width, y2 - height, 0.0)
    if excursion > tolerance:
        return BoxDecision(
            None,
            "reject",
            {
                "reason": "out_of_bounds",
                "bbox": [x, y, w, h],
                "image_size": [width, height],
                "excursion_px": round(excursion, 3),
            },
        )

    cx1, cy1 = max(0.0, x1), max(0.0, y1)
    cx2, cy2 = min(float(width), x2), min(float(height), y2)
    cw, ch = cx2 - cx1, cy2 - cy1
    if cw < min_side or ch < min_side:
        return BoxDecision(
            None,
            "reject",
            {
                "reason": "degenerate",
                "bbox": [x, y, w, h],
                "clipped_wh": [round(cw, 3), round(ch, 3)],
                "min_side": min_side,
            },
        )

    clipped = [cx1, cy1, cw, ch]
    if excursion > 0:
        return BoxDecision(
            clipped,
            "clip",
            {"bbox": [x, y, w, h], "clipped": clipped, "excursion_px": round(excursion, 3)},
        )
    return BoxDecision(clipped, "keep")


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


# --------------------------------------------------------------------------- #
# Image normalization
# --------------------------------------------------------------------------- #
def normalize_image_bytes(raw: bytes) -> tuple[bytes, int, int, bool]:
    """Apply EXIF orientation and strip the tag, re-encoding only when needed.

    Images whose orientation tag is absent or trivial are returned untouched, so
    the overwhelming majority of the dataset stays byte-identical to the source
    and keeps its original hash lineage. Only the rotated ones pay one
    generation of JPEG re-encoding, which is unavoidable: the alternative is
    boxes that do not match their pixels.

    Args:
        raw: original encoded image bytes.

    Returns:
        ``(bytes, width, height, reoriented)`` where ``width``/``height`` are the
        dimensions of the returned bytes.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as image:
        orientation = image.getexif().get(274)
        if orientation in (None, 1):
            return raw, image.width, image.height, False
        fixed = ImageOps.exif_transpose(image)
        if fixed is None:  # pragma: no cover - defensive; transpose returns a copy
            raise BuildError("ImageOps.exif_transpose returned None for an oriented image")
        buffer = io.BytesIO()
        save_format = (image.format or "JPEG").upper()
        if save_format in ("JPEG", "JPG"):
            fixed.convert("RGB").save(
                buffer, format="JPEG", quality=REORIENT_JPEG_QUALITY, optimize=True, exif=b""
            )
        else:
            fixed.save(buffer, format=save_format)
        return buffer.getvalue(), fixed.width, fixed.height, True


def sha256_bytes(data: bytes) -> str:
    """SHA256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    """SHA256 hex digest of the file at ``path``."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Source loading
# --------------------------------------------------------------------------- #
def load_split_manifest(path: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Load ``grouped_split.json``.

    Returns:
        ``(filename -> intended split, the manifest's own metadata)``.

    Raises:
        BuildError: if the file lacks ``filename_split`` or names an unknown split.
    """
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    mapping = manifest.get("filename_split")
    if not isinstance(mapping, dict) or not mapping:
        raise BuildError(f"{path!r} has no non-empty 'filename_split' object")
    unknown = sorted({v for v in mapping.values()} - set(SPLITS))
    if unknown:
        raise BuildError(f"{path!r} assigns unknown split name(s): {unknown}")
    return dict(mapping), manifest


def index_source(source_root: str) -> dict[str, SourceImage]:
    """Index every image in the source deliverable by file name.

    Reads ``annotations/instances_{split}.coco.json`` for boxes and
    ``images/{split}/`` for pixels, for each native split present.

    Raises:
        BuildError: on a missing annotations file, a missing image file, a
            duplicate file name across native splits, or an annotation whose
            ``image_id`` is not in its own file.
    """
    images: dict[str, SourceImage] = {}
    for split in SPLITS:
        ann_path = os.path.join(source_root, "annotations", f"instances_{split}.coco.json")
        img_dir = os.path.join(source_root, "images", split)
        if not os.path.isfile(ann_path):
            raise BuildError(
                f"source annotations not found: {ann_path!r}. Point --source-root at the "
                "deliverable's detection/RICE directory (it must contain "
                "annotations/instances_{train,valid,test}.coco.json and images/<split>/)."
            )
        if not os.path.isdir(img_dir):
            raise BuildError(f"source images not found: {img_dir!r}")
        with open(ann_path, encoding="utf-8") as handle:
            coco = json.load(handle)

        by_image: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        known_ids = {record["id"] for record in coco["images"]}
        for ann in coco["annotations"]:
            if ann["image_id"] not in known_ids:
                raise BuildError(
                    f"{ann_path!r}: annotation {ann.get('id')} references unknown image_id "
                    f"{ann['image_id']}"
                )
            by_image[ann["image_id"]].append(ann)

        for record in coco["images"]:
            name = record["file_name"]
            if name in images:
                raise BuildError(
                    f"file name {name!r} appears in both native splits "
                    f"{images[name].native_split!r} and {split!r}; cannot assign unambiguously"
                )
            path = os.path.join(img_dir, name)
            if not os.path.isfile(path):
                raise BuildError(f"{ann_path!r} lists {name!r} but {path!r} does not exist")
            images[name] = SourceImage(
                file_name=name,
                native_split=split,
                path=path,
                coco_width=int(record["width"]),
                coco_height=int(record["height"]),
                source_sha256=record.get("sha256"),
                annotations=tuple(by_image.get(record["id"], ())),
            )
    return images


def legacy_membership(archive_path: str) -> dict[str, str]:
    """Map file name -> folder for the images inside the legacy phase-2 archive.

    Used only to mark which images were exposed to the voided 2026-07-28 runs, so
    a replacement test split can be drawn from the never-trained-on pool.
    """
    import zipfile

    membership: dict[str, str] = {}
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            parts = info.filename.split("/")
            if len(parts) == 3 and parts[0] == "images" and not parts[2].endswith(".json"):
                membership[parts[2]] = parts[1]
    if not membership:
        raise BuildError(f"{archive_path!r} contains no images/<split>/<file> members")
    return membership


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(
    source_root: str,
    out_root: str,
    *,
    split_manifest: str | None = None,
    legacy_archive: str | None = None,
    block_size: int = DEFAULT_BLOCK_SIZE,
    keep_segmentation: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Materialize the grouped split from the source deliverable.

    Args:
        source_root: the deliverable's ``detection/RICE`` directory.
        out_root: output directory; created if absent.
        split_manifest: path to ``grouped_split.json``; defaults to the one inside
            ``source_root``.
        legacy_archive: optional path to ``RICE_curated_phase2.zip``, used to flag
            which emitted images were already trained on.
        block_size: frame-block size for :func:`derive_group_id`.
        keep_segmentation: keep the SAM-derived polygons. Off by default: they are
            marked ``review_status: unreviewed`` in the source provenance and this
            is a box-detection dataset.
        overwrite: allow writing into a non-empty ``out_root``.

    Returns:
        The build report (also written to ``reports/build_report.json``).

    Raises:
        BuildError: on any manifest/source disagreement, dimension mismatch, or
            count mismatch against the manifest's own ``per_split`` totals.
    """
    split_manifest = split_manifest or os.path.join(source_root, "grouped_split.json")
    assignment, manifest_meta = load_split_manifest(split_manifest)
    source = index_source(source_root)

    missing = sorted(set(assignment) - set(source))
    if missing:
        raise BuildError(
            f"{len(missing)} file(s) named by {split_manifest!r} are absent from "
            f"{source_root!r}, e.g. {missing[:3]}. The source deliverable must be "
            "complete -- this is exactly the defect that produced the contaminated "
            "archive (its build dropped the native test/ folder, losing 233 intended "
            "train/valid images)."
        )
    extra = sorted(set(source) - set(assignment))
    if extra:
        raise BuildError(
            f"{len(extra)} source image(s) are not assigned by {split_manifest!r}, e.g. "
            f"{extra[:3]}. Every source image must have an intended split."
        )

    if os.path.isdir(out_root) and os.listdir(out_root) and not overwrite:
        raise BuildError(f"{out_root!r} is not empty; pass --overwrite to rebuild in place")

    legacy = legacy_membership(legacy_archive) if legacy_archive else {}

    emitted: dict[str, list[EmittedImage]] = {split: [] for split in SPLITS}
    rejected: list[dict[str, Any]] = []
    clipped: list[dict[str, Any]] = []
    coco_by_split: dict[str, dict[str, Any]] = {}
    # Counts as they exist in the source, before sanitation. The split manifest's
    # per_split block describes *these*, so the faithfulness check compares against
    # them and sanitation is reported separately as a delta.
    raw_counts: dict[str, Counter[str]] = {split: Counter() for split in SPLITS}
    reoriented_total = 0
    name_by_category = {category["id"]: category["name"] for category in CATEGORIES}

    for split in SPLITS:
        names = sorted(name for name, target in assignment.items() if target == split)
        os.makedirs(os.path.join(out_root, "images", split), exist_ok=True)
        coco_images: list[dict[str, Any]] = []
        coco_anns: list[dict[str, Any]] = []

        for image_id, name in enumerate(names, start=1):
            item = source[name]
            with open(item.path, "rb") as handle:
                raw = handle.read()
            data, width, height, reoriented = normalize_image_bytes(raw)
            if (width, height) != (item.coco_width, item.coco_height):
                raise BuildError(
                    f"{name!r}: normalized pixels are {width}x{height} but its COCO record "
                    f"says {item.coco_width}x{item.coco_height}. Orientation normalization "
                    "did not reconcile this image; inspect it before continuing."
                )
            out_path = os.path.join(out_root, "images", split, name)
            with open(out_path, "wb") as handle:
                handle.write(data)

            reoriented_total += int(reoriented)
            record = EmittedImage(
                file_name=name,
                split=split,
                native_split=item.native_split,
                group_id=derive_group_id(name, block_size),
                width=width,
                height=height,
                sha256=sha256_bytes(data),
                bytes_written=len(data),
                reoriented=reoriented,
                source_sha256=item.source_sha256,
                trained_on_legacy=(legacy.get(name) == "train") if legacy else None,
            )
            emitted[split].append(record)

            coco_images.append(
                {
                    "id": image_id,
                    "file_name": name,
                    "width": width,
                    "height": height,
                    "sha256": record.sha256,
                    "source_split": item.native_split,
                    "group_id": record.group_id,
                    "exif_reoriented": reoriented,
                }
            )
            for ann in item.annotations:
                raw_counts[split][name_by_category.get(int(ann["category_id"]), "?")] += 1
                decision = sanitize_box(ann["bbox"], width, height)
                entry = {
                    "file_name": name,
                    "split": split,
                    "source_annotation_id": ann.get("id"),
                    "category_id": ann["category_id"],
                    **decision.detail,
                }
                if decision.bbox is None:
                    rejected.append({"action": "reject", **entry})
                    continue
                if decision.action == "clip":
                    clipped.append({"action": "clip", **entry})
                x, y, w, h = decision.bbox
                new_ann: dict[str, Any] = {
                    "id": len(coco_anns) + 1,
                    "image_id": image_id,
                    "category_id": int(ann["category_id"]),
                    "bbox": [x, y, w, h],
                    "area": w * h,
                    "iscrowd": int(ann.get("iscrowd", 0)),
                }
                if keep_segmentation and ann.get("segmentation"):
                    new_ann["segmentation"] = ann["segmentation"]
                coco_anns.append(new_ann)

        coco_by_split[split] = {
            "info": {
                "description": f"AgriNav phase-2 curated RICE detector dataset -- {split}",
                "split": split,
                "built_by": "agrinav.data.build_rice_phase2",
                "grouping_method": manifest_meta.get("method"),
                "segmentation_dropped": not keep_segmentation,
                "segmentation_note": (
                    "SAM2 box-prompted polygons exist in the source "
                    "(annotations/instances_*.coco.json) but are marked "
                    "review_status: unreviewed; this is a box-detection dataset."
                ),
            },
            "licenses": [],
            "categories": [dict(category) for category in CATEGORIES],
            "images": coco_images,
            "annotations": coco_anns,
        }

    reconciliation = _check_expected_counts(coco_by_split, raw_counts, rejected, manifest_meta)
    report = _write_outputs(
        out_root,
        coco_by_split,
        emitted,
        rejected,
        clipped,
        reconciliation=reconciliation,
        manifest_meta=manifest_meta,
        source_root=source_root,
        split_manifest=split_manifest,
        legacy_archive=legacy_archive,
        keep_segmentation=keep_segmentation,
        reoriented_total=reoriented_total,
    )
    return report


def _check_expected_counts(
    coco_by_split: dict[str, dict[str, Any]],
    raw_counts: dict[str, Counter[str]],
    rejected: list[dict[str, Any]],
    manifest_meta: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile source-side counts with the manifest, and account for sanitation.

    The manifest's ``per_split`` block counts the *source* boxes, so the
    faithfulness check compares those. Sanitation removals are then reported as an
    explicit, itemized delta rather than being absorbed silently.

    Returns:
        A reconciliation table: per split, ``manifest`` / ``source_assigned`` /
        ``rejected`` / ``emitted`` counts.

    Raises:
        BuildError: if the source-side assignment disagrees with the manifest, or
            if ``emitted + rejected != source_assigned`` for any class.
    """
    name_by_id = {category["id"]: category["name"] for category in CATEGORIES}
    raw_expected = manifest_meta.get("per_split")
    expected: dict[str, dict[str, Any]] = raw_expected if isinstance(raw_expected, dict) else {}
    rejected_per_split: dict[str, Counter[str]] = {split: Counter() for split in SPLITS}
    for item in rejected:
        label = name_by_id.get(int(item["category_id"]), "?")
        rejected_per_split[item["split"]][label] += 1

    table: dict[str, Any] = {}
    problems: list[str] = []
    for split in SPLITS:
        doc = coco_by_split[split]
        emitted_per_class = Counter(name_by_id[ann["category_id"]] for ann in doc["annotations"])
        want = expected.get(split, {})
        row: dict[str, dict[str, Any]] = {
            "manifest": {
                "images": want.get("images"),
                "rice_protect": want.get("rice"),
                "weed_target": want.get("weed"),
            },
            "source_assigned": {
                "images": len(doc["images"]),
                "rice_protect": raw_counts[split].get("rice_protect", 0),
                "weed_target": raw_counts[split].get("weed_target", 0),
            },
            "rejected_by_sanitation": {
                "rice_protect": rejected_per_split[split].get("rice_protect", 0),
                "weed_target": rejected_per_split[split].get("weed_target", 0),
            },
            "emitted": {
                "images": len(doc["images"]),
                "rice_protect": emitted_per_class.get("rice_protect", 0),
                "weed_target": emitted_per_class.get("weed_target", 0),
            },
        }
        table[split] = row

        for key in ("images", "rice_protect", "weed_target"):
            want_value = row["manifest"][key]
            if want_value is not None and int(want_value) != row["source_assigned"][key]:
                problems.append(
                    f"{split}.{key}: manifest {want_value} != source-assigned "
                    f"{row['source_assigned'][key]}"
                )
        for key in ("rice_protect", "weed_target"):
            balance = row["emitted"][key] + row["rejected_by_sanitation"][key]
            if balance != row["source_assigned"][key]:
                problems.append(
                    f"{split}.{key}: emitted {row['emitted'][key]} + rejected "
                    f"{row['rejected_by_sanitation'][key]} != source-assigned "
                    f"{row['source_assigned'][key]}"
                )

    if problems:
        raise BuildError(
            "count reconciliation failed:\n  "
            + "\n  ".join(problems)
            + "\nA manifest-vs-source disagreement means the wrong source or manifest was "
            "passed. An emitted-vs-rejected imbalance is a bug in this module."
        )
    return table


def _write_outputs(
    out_root: str,
    coco_by_split: dict[str, dict[str, Any]],
    emitted: dict[str, list[EmittedImage]],
    rejected: list[dict[str, Any]],
    clipped: list[dict[str, Any]],
    *,
    reconciliation: dict[str, Any],
    manifest_meta: dict[str, Any],
    source_root: str,
    split_manifest: str,
    legacy_archive: str | None,
    keep_segmentation: bool,
    reoriented_total: int,
) -> dict[str, Any]:
    """Write annotations, manifests, reports, and the burned-test notice."""
    for directory in ("annotations", "manifests", "reports"):
        os.makedirs(os.path.join(out_root, directory), exist_ok=True)

    json_hashes: dict[str, str] = {}
    for split, doc in coco_by_split.items():
        rel = f"annotations/instances_{split}.coco.json"
        path = os.path.join(out_root, rel)
        _dump_json(path, doc)
        json_hashes[rel] = sha256_file(path)

    # Copy the split manifest into the tree so a consumer -- a Colab session, a
    # reviewer, CI -- can run `preflight` against the archive alone, with no
    # dependency on a path that only exists on the build machine.
    vendored_manifest = os.path.join(out_root, "manifests", "grouped_split.json")
    with open(split_manifest, "rb") as source_handle:
        manifest_bytes = source_handle.read()
    with open(vendored_manifest, "wb") as target_handle:
        target_handle.write(manifest_bytes)
    json_hashes["manifests/grouped_split.json"] = sha256_bytes(manifest_bytes)

    membership: dict[str, dict[str, Any]] = {
        record.file_name: {
            "split": record.split,
            "native_split": record.native_split,
            "group_id": record.group_id,
            "width": record.width,
            "height": record.height,
            "sha256": record.sha256,
            "bytes": record.bytes_written,
            "exif_reoriented": record.reoriented,
            "source_sha256": record.source_sha256,
            "trained_on_legacy": record.trained_on_legacy,
        }
        for records in emitted.values()
        for record in records
    }
    _dump_json(os.path.join(out_root, "manifests", "split_membership.json"), membership)
    json_hashes["manifests/split_membership.json"] = sha256_file(
        os.path.join(out_root, "manifests", "split_membership.json")
    )

    _dump_json(
        os.path.join(out_root, "reports", "rejected_annotations.json"),
        {
            "rule": {
                "clip_tolerance_px": 1.0,
                "min_side_px": 1.0,
                "note": "identical rule for training inputs and evaluation ground truth",
            },
            "counts": {
                "rejected": len(rejected),
                "clipped": len(clipped),
                "rejected_by_reason": dict(Counter(item.get("reason", "?") for item in rejected)),
            },
            "rejected": rejected,
            "clipped": clipped,
        },
    )

    groups_by_split: dict[str, set[str]] = {
        split: {record.group_id for record in records} for split, records in emitted.items()
    }
    cross_group = {
        f"{a}|{b}": sorted(groups_by_split[a] & groups_by_split[b])
        for a, b in (("train", "valid"), ("train", "test"), ("valid", "test"))
        if groups_by_split[a] & groups_by_split[b]
    }
    hash_index: dict[str, list[str]] = defaultdict(list)
    for name, entry in membership.items():
        hash_index[entry["sha256"]].append(name)
    duplicate_hashes = {digest: names for digest, names in hash_index.items() if len(names) > 1}

    per_split = {
        split: {
            "images": len(coco_by_split[split]["images"]),
            "annotations": len(coco_by_split[split]["annotations"]),
            "rice_protect": sum(
                1 for ann in coco_by_split[split]["annotations"] if ann["category_id"] == 1
            ),
            "weed_target": sum(
                1 for ann in coco_by_split[split]["annotations"] if ann["category_id"] == 2
            ),
            "groups": len(groups_by_split[split]),
            "exif_reoriented": sum(1 for record in emitted[split] if record.reoriented),
            "trained_on_legacy": sum(
                1 for record in emitted[split] if record.trained_on_legacy is True
            ),
            "never_trained_on": sum(
                1 for record in emitted[split] if record.trained_on_legacy is False
            ),
        }
        for split in SPLITS
    }

    provenance = {
        "built_by": "agrinav.data.build_rice_phase2",
        "source_root": os.path.abspath(source_root),
        "split_manifest": os.path.abspath(split_manifest),
        "split_manifest_sha256": sha256_file(split_manifest),
        "grouping_method": manifest_meta.get("method"),
        "legacy_archive": os.path.abspath(legacy_archive) if legacy_archive else None,
        "legacy_archive_sha256": sha256_file(legacy_archive) if legacy_archive else None,
        "boxes": "human-reviewed COCO boxes from annotations/instances_*.coco.json",
        "segmentation_kept": keep_segmentation,
        "exif_policy": (
            "ImageOps.exif_transpose applied and the EXIF block stripped; only rotated "
            f"images re-encoded (JPEG q={REORIENT_JPEG_QUALITY}), all others byte-identical "
            "to source"
        ),
        "images_reoriented": reoriented_total,
        "group_id_note": (
            "group_id is RE-DERIVED by derive_group_id() (capture-family stem + "
            "frame // block_size). The source manifest does not store per-file group ids, "
            "so this is not the provenance of the train/valid assignment."
        ),
        "test_split_status": (
            "VALID for a model trained from scratch on this build; NEVER for the "
            "2026-07-28 checkpoints, which trained on part of it. "
            "See TEST_SPLIT_STATUS.md"
        ),
        "json_sha256": json_hashes,
        "per_split": per_split,
        "manifest_reconciliation": reconciliation,
    }
    _dump_json(os.path.join(out_root, "manifests", "provenance.json"), provenance)

    report = {
        "out_root": os.path.abspath(out_root),
        "per_split": per_split,
        "manifest_reconciliation": reconciliation,
        "totals": {
            "images": sum(value["images"] for value in per_split.values()),
            "annotations": sum(value["annotations"] for value in per_split.values()),
            "exif_reoriented": reoriented_total,
            "annotations_rejected": len(rejected),
            "annotations_clipped": len(clipped),
        },
        "leakage": {
            "cross_split_derived_group_overlap": cross_group,
            "duplicate_image_hashes": duplicate_hashes,
        },
        "json_sha256": json_hashes,
    }
    _dump_json(os.path.join(out_root, "reports", "build_report.json"), report)
    _write_burned_notice(out_root, per_split)
    return report


def _write_burned_notice(out_root: str, per_split: dict[str, dict[str, int]]) -> None:
    """Write the notice explaining who may and may not evaluate on the test split."""
    trained = per_split["test"].get("trained_on_legacy", 0)
    total = per_split["test"]["images"]
    text = f"""# The `test` split: usable for a fresh model, not for the 2026-07-28 checkpoints

`RICE_curated_phase2.zip` mis-exported {trained} of these {total} images into its
train folder, and two phase-2 runs (2026-07-28, both voided) trained on that
archive.

But **no metric was ever computed on these images.** No evaluator existed in the
repository until 2026-07-29 -- checkpoint selection ran on training loss, then
validation loss. Nothing was tuned, chosen, or reported against this split.

Contamination is a property of the **weights**, not the images:

- **The 2026-07-28 checkpoints may never be evaluated on this split.** They
  memorized {trained} of its images. Both runs are void for other reasons anyway.
- **A model trained from scratch on this rebuilt dataset may use it normally.**
  Those weights have never seen it, and no selection decision was informed by it.

## Why not build a replacement from the never-trained-on images

`manifests/split_membership.json` carries, per image, `trained_on_legacy` (`true`
if it was in the legacy archive's train folder, `null` if no legacy archive was
passed) and `group_id`, a **re-derived** capture-family + frame-block key --
`grouped_split.json` records `num_groups` and `block_size` but no per-file ids,
so the original grouping cannot be reproduced.

Measured on the 2026-07-29 build: of the 781 never-trained-on images, 83 of the
89 groups they span *also* contain a trained-on image, leaving only 6 images in a
fully clean group -- and those 6 carry zero weed boxes. A group-respecting test
split drawn from the clean pool is empty in practice. Selecting at the image
level instead would reintroduce exactly the leakage grouping exists to prevent:
adjacent frames of one capture sequence in train and test at once.

## What still needs care

- Freeze the operating threshold on validation, then evaluate the test split once.
- 3 re-derived groups straddle a split boundary, because the source cut video
  sequences into 40-frame blocks. Guard-band the edges or state the residual.
- None of this supports a *generalization* claim: the manifest carries no farm,
  season, device, or illumination metadata. An external set is separate work.
"""
    with open(os.path.join(out_root, "TEST_SPLIT_STATUS.md"), "w", encoding="utf-8") as handle:
        handle.write(text)


def _dump_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #
def preflight(out_root: str, *, split_manifest: str | None = None) -> dict[str, Any]:
    """Re-verify a built dataset from disk. Independent of the build's own state.

    Checks, per split: every COCO image exists on disk, its bytes hash to the
    recorded ``sha256``, its decoded dimensions match the record, every
    annotation is inside bounds with positive area and a known category, and no
    file name or content hash appears in two splits. Also cross-checks emitted
    membership against ``split_manifest`` when one is given.

    Args:
        out_root: a directory produced by :func:`build`.
        split_manifest: optional ``grouped_split.json`` to compare membership
            against. Defaults to the path recorded in ``manifests/provenance.json``.

    Returns:
        The preflight report (also written to ``reports/preflight.json``).

    Raises:
        BuildError: on the first category of failure found, listing examples.
    """
    from PIL import Image

    provenance_path = os.path.join(out_root, "manifests", "provenance.json")
    provenance: dict[str, Any] = {}
    if os.path.isfile(provenance_path):
        with open(provenance_path, encoding="utf-8") as handle:
            provenance = json.load(handle)
    # Prefer the manifest vendored into the tree: the absolute path recorded in
    # provenance only resolves on the machine that built it.
    vendored = os.path.join(out_root, "manifests", "grouped_split.json")
    if split_manifest is None and os.path.isfile(vendored):
        split_manifest = vendored
    split_manifest = split_manifest or provenance.get("split_manifest")

    failures: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, dict[str, int]] = {}
    seen_names: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    valid_categories = {category["id"] for category in CATEGORIES}

    present_splits: list[str] = []
    for split in SPLITS:
        ann_path = os.path.join(out_root, "annotations", f"instances_{split}.coco.json")
        image_dir = os.path.join(out_root, "images", split)
        if not os.path.isfile(ann_path):
            # A packaged training archive deliberately omits the test split, so an
            # absent split is normal. Images with no annotations file is not.
            if os.path.isdir(image_dir) and os.listdir(image_dir):
                failures["images_without_annotations"].append(image_dir)
            continue
        present_splits.append(split)
        with open(ann_path, encoding="utf-8") as handle:
            doc = json.load(handle)
        dims: dict[Any, tuple[int, int]] = {}
        for record in doc["images"]:
            name = record["file_name"]
            path = os.path.join(out_root, "images", split, name)
            dims[record["id"]] = (record["width"], record["height"])
            if name in seen_names:
                failures["file_in_two_splits"].append(f"{name} in {seen_names[name]} and {split}")
            seen_names[name] = split
            if not os.path.isfile(path):
                failures["image_missing"].append(path)
                continue
            digest = sha256_file(path)
            if record.get("sha256") and digest != record["sha256"]:
                failures["hash_mismatch"].append(f"{split}/{name}")
            if digest in seen_hashes and seen_hashes[digest] != f"{split}/{name}":
                failures["duplicate_content"].append(f"{split}/{name} == {seen_hashes[digest]}")
            seen_hashes.setdefault(digest, f"{split}/{name}")
            with Image.open(path) as image:
                if image.size != (record["width"], record["height"]):
                    failures["dimension_mismatch"].append(
                        f"{split}/{name}: file {image.size} != record "
                        f"({record['width']}, {record['height']})"
                    )
                if image.getexif().get(274) not in (None, 1):
                    failures["exif_orientation_present"].append(f"{split}/{name}")

        for ann in doc["annotations"]:
            if ann["category_id"] not in valid_categories:
                failures["unknown_category"].append(f"{split}: ann {ann['id']}")
            if ann["image_id"] not in dims:
                failures["orphan_annotation"].append(f"{split}: ann {ann['id']}")
                continue
            width, height = dims[ann["image_id"]]
            x, y, w, h = ann["bbox"]
            if w <= 0 or h <= 0:
                failures["nonpositive_box"].append(f"{split}: ann {ann['id']}")
            if x < 0 or y < 0 or x + w > width + 1e-6 or y + h > height + 1e-6:
                failures["out_of_bounds_box"].append(f"{split}: ann {ann['id']}")

        # Files on disk that no COCO record claims: a half-finished or hand-edited
        # build. Invisible to every record-driven check above, so check it directly.
        image_dir = os.path.join(out_root, "images", split)
        if os.path.isdir(image_dir):
            claimed = {record["file_name"] for record in doc["images"]}
            stray = sorted(set(os.listdir(image_dir)) - claimed)
            failures["unclaimed_file_on_disk"].extend(f"{split}/{name}" for name in stray)

        counts[split] = {
            "images": len(doc["images"]),
            "annotations": len(doc["annotations"]),
            "rice_protect": sum(1 for a in doc["annotations"] if a["category_id"] == 1),
            "weed_target": sum(1 for a in doc["annotations"] if a["category_id"] == 2),
        }

    if not present_splits:
        raise BuildError(
            f"{out_root!r} contains no annotations/instances_<split>.coco.json; "
            "it is not a build produced by this module."
        )

    manifest_check: dict[str, Any] = {"checked": False}
    if split_manifest and os.path.isfile(split_manifest):
        assignment, manifest_meta = load_split_manifest(split_manifest)
        mismatches = [
            f"{name}: manifest {want} != emitted {seen_names[name]}"
            for name, want in assignment.items()
            if name in seen_names and seen_names[name] != want
        ]
        # Only hold the build to account for splits it actually contains: a
        # training archive legitimately omits test, and its images with it.
        expected_here = {name for name, want in assignment.items() if want in set(present_splits)}
        absent = sorted(expected_here - set(seen_names))
        unexpected = sorted(set(seen_names) - set(assignment))
        manifest_check = {
            "checked": True,
            "split_manifest": split_manifest,
            "splits_present": present_splits,
            "splits_absent": [split for split in SPLITS if split not in present_splits],
            "assignment_mismatches": len(mismatches),
            "manifest_images_not_emitted": len(absent),
            "emitted_images_not_in_manifest": len(unexpected),
        }
        if mismatches:
            failures["assignment_mismatch"].extend(mismatches[:20])
        if absent:
            failures["manifest_image_not_emitted"].extend(absent[:20])
        if unexpected:
            failures["emitted_image_not_in_manifest"].extend(unexpected[:20])
        _check_counts_against_manifest(counts, manifest_meta, provenance, failures)

    # `failures` is a defaultdict fed by `.extend()`, which can create an empty
    # list for a category that found nothing; drop those before deciding.
    failures = {key: values for key, values in failures.items() if values}
    report = {
        "out_root": os.path.abspath(out_root),
        "splits_present": present_splits,
        "counts": counts,
        "manifest_check": manifest_check,
        "failures": {key: values[:20] for key, values in failures.items()},
        "failure_counts": {key: len(values) for key, values in failures.items()},
        "passed": not failures,
    }
    reports_dir = os.path.join(out_root, "reports")
    if os.path.isdir(reports_dir):
        _dump_json(os.path.join(reports_dir, "preflight.json"), report)
    if failures:
        summary = "; ".join(f"{key}={len(values)}" for key, values in sorted(failures.items()))
        example = next(iter(failures.values()))[0]
        raise BuildError(
            f"preflight FAILED for {out_root!r}: {summary}. First example: {example}. "
            "Full report: reports/preflight.json"
        )
    return report


def _check_counts_against_manifest(
    counts: dict[str, dict[str, int]],
    manifest_meta: dict[str, Any],
    provenance: dict[str, Any],
    failures: dict[str, list[str]],
) -> None:
    """Check ``emitted + recorded sanitation removals == manifest``, per split and class.

    Image counts must match the manifest exactly. Box counts may legitimately be
    lower by exactly the number of annotations the build recorded as rejected, so
    the check adds those back from ``manifests/provenance.json``; a build with no
    recorded reconciliation is required to match exactly.
    """
    expected = manifest_meta.get("per_split")
    if not isinstance(expected, dict):
        return
    reconciliation = provenance.get("manifest_reconciliation") or {}
    for split, want in expected.items():
        got = counts.get(split)
        if not got:
            continue
        want_images = want.get("images")
        if want_images is not None and int(want_images) != got["images"]:
            failures["count_mismatch"].append(
                f"{split}.images: manifest {want_images} != emitted {got['images']}"
            )
        removals = (reconciliation.get(split) or {}).get("rejected_by_sanitation", {})
        for manifest_key, emitted_key in (("rice", "rice_protect"), ("weed", "weed_target")):
            want_value = want.get(manifest_key)
            if want_value is None:
                continue
            removed = int(removals.get(emitted_key, 0))
            if int(want_value) != got[emitted_key] + removed:
                failures["count_mismatch"].append(
                    f"{split}.{manifest_key}: manifest {want_value} != emitted "
                    f"{got[emitted_key]} + recorded sanitation removals {removed}"
                )


# --------------------------------------------------------------------------- #
# Packaging
# --------------------------------------------------------------------------- #
def package(out_root: str, zip_path: str, *, include_test: bool = False) -> dict[str, Any]:
    """Zip a built dataset for upload, excluding the test split by default.

    Args:
        out_root: a directory produced by :func:`build` (and passed :func:`preflight`).
        zip_path: destination ``.zip``.
        include_test: include ``images/test`` and ``instances_test.coco.json``.

    Returns:
        ``{"path", "bytes", "sha256", "members", "includes_test"}``.
    """
    import zipfile

    os.makedirs(os.path.dirname(os.path.abspath(zip_path)) or ".", exist_ok=True)
    members = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(out_root):
            for name in sorted(files):
                absolute = os.path.join(root, name)
                relative = os.path.relpath(absolute, out_root).replace(os.sep, "/")
                if not include_test and (
                    relative.startswith("images/test/") or "instances_test" in relative
                ):
                    continue
                archive.write(absolute, relative)
                members += 1
    return {
        "path": os.path.abspath(zip_path),
        "bytes": os.path.getsize(zip_path),
        "sha256": sha256_file(zip_path),
        "members": members,
        "includes_test": include_test,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_report(report: dict[str, Any]) -> None:
    print(f"built -> {report['out_root']}")
    header = (
        f"  {'split':<7}{'images':>8}{'boxes':>9}{'rice':>9}{'weed':>8}{'groups':>8}{'exif':>7}"
    )
    print(header)
    for split, value in report["per_split"].items():
        print(
            f"  {split:<7}{value['images']:>8}{value['annotations']:>9}"
            f"{value['rice_protect']:>9}{value['weed_target']:>8}"
            f"{value['groups']:>8}{value['exif_reoriented']:>7}"
        )
    totals = report["totals"]
    print(
        f"  totals: {totals['images']} images, {totals['annotations']} boxes, "
        f"{totals['exif_reoriented']} reoriented, {totals['annotations_rejected']} rejected, "
        f"{totals['annotations_clipped']} clipped"
    )
    overlap = report["leakage"]["cross_split_derived_group_overlap"]
    dupes = report["leakage"]["duplicate_image_hashes"]
    print(f"  derived-group overlap across splits: {len(overlap)} pair(s) affected")
    print(f"  duplicate image hashes: {len(dupes)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agrinav data-build-rice-phase2",
        description=(
            "Rebuild the phase-2 curated-RICE detector dataset from the source "
            "deliverable: apply grouped_split.json, normalize EXIF orientation, hash "
            "everything, and verify the result from disk."
        ),
    )
    sub = parser.add_subparsers(dest="action", required=True)

    build_parser = sub.add_parser("build", help="materialize the grouped split")
    build_parser.add_argument(
        "--source-root", required=True, help="deliverable's detection/RICE directory"
    )
    build_parser.add_argument("--out-root", required=True, help="output directory")
    build_parser.add_argument(
        "--split-manifest", default=None, help="grouped_split.json (default: inside --source-root)"
    )
    build_parser.add_argument(
        "--legacy-archive",
        default=None,
        help="old RICE_curated_phase2.zip; flags which images were already trained on",
    )
    build_parser.add_argument(
        "--block-size", type=int, default=DEFAULT_BLOCK_SIZE, help="frame block size for group ids"
    )
    build_parser.add_argument(
        "--keep-segmentation",
        action="store_true",
        help="keep the unreviewed SAM polygons (off by default)",
    )
    build_parser.add_argument(
        "--overwrite", action="store_true", help="allow a non-empty --out-root"
    )
    build_parser.add_argument(
        "--skip-preflight", action="store_true", help="do not verify after building"
    )

    check_parser = sub.add_parser("preflight", help="verify an existing build from disk")
    check_parser.add_argument("--out-root", required=True)
    check_parser.add_argument("--split-manifest", default=None)

    pack_parser = sub.add_parser("package", help="zip a verified build for upload")
    pack_parser.add_argument("--out-root", required=True)
    pack_parser.add_argument("--zip", required=True, dest="zip_path")
    pack_parser.add_argument(
        "--include-test",
        action="store_true",
        help="include the burned test split (excluded by default)",
    )

    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            report = build(
                args.source_root,
                args.out_root,
                split_manifest=args.split_manifest,
                legacy_archive=args.legacy_archive,
                block_size=args.block_size,
                keep_segmentation=args.keep_segmentation,
                overwrite=args.overwrite,
            )
            _print_report(report)
            if not args.skip_preflight:
                result = preflight(args.out_root, split_manifest=args.split_manifest)
                print(f"  preflight: PASSED ({result['counts']})")
        elif args.action == "preflight":
            result = preflight(args.out_root, split_manifest=args.split_manifest)
            print(f"preflight PASSED for {result['out_root']}")
            for split, counts in result["counts"].items():
                print(f"  {split:<7}{counts}")
        else:
            result = package(args.out_root, args.zip_path, include_test=args.include_test)
            print(f"packaged -> {result['path']}")
            print(f"  bytes  : {result['bytes']}")
            print(f"  sha256 : {result['sha256']}")
            print(f"  members: {result['members']}  includes_test={result['includes_test']}")
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
