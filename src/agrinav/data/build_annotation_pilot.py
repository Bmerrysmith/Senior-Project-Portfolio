#!/usr/bin/env python3
"""Build a deterministic, review-only annotation pilot from two source ZIPs.

The utility never extracts or modifies either source archive. RiceSEG masks are
read directly from the ZIP to compute class histograms, and the Roboflow COCO
JSON is read directly to compute proposal statistics. Selected media are only
copied when ``--materialize-dir`` is explicitly supplied.

All upstream annotations remain proposals until a human reviewer accepts them.
In particular, an image with no proposal is *not* marked as a verified empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from PIL import Image

SCHEMA_VERSION = "agrinav.annotation_pilot.v1"
DEFAULT_TARGET_SIZE = 200
DEFAULT_GOLD_SIZE = 40
DEFAULT_SEED = 20260720
PUBLIC_MIN_PILOT = 150
PUBLIC_MAX_PILOT = 300
MAX_ARCHIVE_ENTRIES = 1_000_000
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_IMAGE_BYTES = 64 * 1024 * 1024

RICESEG_CLASS_NAMES = {
    0: "background",
    1: "green_rice",
    2: "senescent_rice",
    3: "rice_panicle",
    4: "weed",
    5: "duckweed",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
ROBOFLOW_LINEAGE_RE = re.compile(r"\.rf\.[0-9a-f]+$", re.IGNORECASE)
TILE_SUFFIX_RE = re.compile(r"^(?P<source>.+)_subset_overlap_\d+_\d+$", re.IGNORECASE)


class PilotBuildError(ValueError):
    """Raised when an archive violates an expected structural invariant."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_zip_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    chunk_size: int = 1024 * 1024,
) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_member(name: str) -> str:
    normalised = name.replace("\\", "/")
    path = PurePosixPath(normalised)
    if path.is_absolute() or ".." in path.parts:
        raise PilotBuildError(f"Unsafe ZIP member path: {name!r}")
    return str(path)


def _zip_member_map(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise PilotBuildError(
            f"Archive has {len(infos):,} entries; limit is {MAX_ARCHIVE_ENTRIES:,}"
        )
    members: dict[str, zipfile.ZipInfo] = {}
    lower_names: set[str] = set()
    for info in infos:
        if info.is_dir():
            continue
        name = _normalise_member(info.filename)
        lower = name.casefold()
        if lower in lower_names:
            raise PilotBuildError(f"Duplicate case-insensitive ZIP member: {name}")
        lower_names.add(lower)
        members[name] = info
    return members


def _require_small_member(info: zipfile.ZipInfo, *, kind: str) -> None:
    if info.file_size > MAX_IMAGE_BYTES:
        raise PilotBuildError(
            f"{kind} member {info.filename!r} expands to {info.file_size:,} bytes; "
            f"limit is {MAX_IMAGE_BYTES:,}"
        )


def _source_photo_id(stem: str) -> str:
    match = TILE_SUFFIX_RE.match(stem)
    return match.group("source") if match else stem


def _parse_riceseg_member(member: str) -> tuple[str, str | None, str, str] | None:
    """Return country, site, kind and filename for a RiceSEG media member."""
    parts = PurePosixPath(member).parts
    kind_index = next(
        (index for index, part in enumerate(parts) if part.casefold() in {"rgb", "label"}),
        None,
    )
    if kind_index is None or kind_index < 2 or kind_index != len(parts) - 2:
        return None
    country = parts[kind_index - 2] if kind_index >= 3 else parts[kind_index - 1]
    site = parts[kind_index - 1] if kind_index >= 3 else None
    # The first component is the dataset root, so country-only paths have rgb at 2.
    if kind_index == 2:
        country = parts[1]
        site = None
    kind = parts[kind_index].casefold()
    return country, site, kind, parts[-1]


def _mask_histogram(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> tuple[int, int, dict[int, int]]:
    _require_small_member(info, kind="RiceSEG mask")
    with archive.open(info, "r") as stream:
        with Image.open(stream) as mask:
            mask.load()
            if mask.mode not in {"1", "L", "P", "I", "I;16", "I;16L", "I;16B"}:
                raise PilotBuildError(
                    f"RiceSEG mask {info.filename!r} must be single-channel, got {mask.mode!r}"
                )
            extrema = mask.getextrema()
            if isinstance(extrema[0], tuple):
                raise PilotBuildError(f"RiceSEG mask {info.filename!r} is not scalar")
            if extrema[0] < 0 or extrema[1] > 255:
                raise PilotBuildError(
                    f"RiceSEG mask {info.filename!r} has values outside [0, 255]: {extrema}"
                )
            histogram = mask.convert("L").histogram()
            unknown = [
                value
                for value, count in enumerate(histogram)
                if count and value not in RICESEG_CLASS_NAMES
            ]
            if unknown:
                raise PilotBuildError(
                    f"RiceSEG mask {info.filename!r} has unknown class values: {unknown}"
                )
            counts = {value: histogram[value] for value in RICESEG_CLASS_NAMES}
            return mask.width, mask.height, counts


def _image_dimensions(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    kind: str,
) -> tuple[int, int]:
    """Read and verify an image member without extracting it."""
    _require_small_member(info, kind=kind)
    try:
        with archive.open(info, "r") as stream:
            with Image.open(stream) as image:
                width, height = image.size
                image.verify()
    except (OSError, ValueError) as exc:
        raise PilotBuildError(f"Invalid {kind} {info.filename!r}: {exc}") from exc
    if width <= 0 or height <= 0:
        raise PilotBuildError(f"{kind} {info.filename!r} has invalid size {width}x{height}")
    return width, height


def inventory_riceseg(zip_path: Path | str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Inventory paired RiceSEG RGB/mask tiles without extracting the archive."""
    zip_path = Path(zip_path)
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = _zip_member_map(archive)
        pairs: dict[tuple[str, str | None, str], dict[str, str]] = defaultdict(dict)
        for member in members:
            parsed = _parse_riceseg_member(member)
            if parsed is None:
                continue
            country, site, kind, filename = parsed
            if Path(filename).suffix.casefold() not in IMAGE_SUFFIXES:
                continue
            key = (country, site, Path(filename).stem.casefold())
            if kind in pairs[key]:
                raise PilotBuildError(f"Duplicate RiceSEG {kind} item for {key}")
            pairs[key][kind] = member

        incomplete = [key for key, pair in pairs.items() if set(pair) != {"rgb", "label"}]
        if incomplete:
            preview = ", ".join(repr(item) for item in incomplete[:5])
            raise PilotBuildError(
                f"RiceSEG has {len(incomplete)} incomplete RGB/mask pair(s), including {preview}"
            )
        if not pairs:
            raise PilotBuildError("No paired RiceSEG rgb/label media found")

        for (country, site, _), pair in sorted(
            pairs.items(),
            key=lambda item: tuple("" if value is None else value.casefold() for value in item[0]),
        ):
            image_member = pair["rgb"]
            mask_member = pair["label"]
            width, height, raw_counts = _mask_histogram(archive, members[mask_member])
            image_width, image_height = _image_dimensions(
                archive,
                members[image_member],
                kind="RiceSEG RGB image",
            )
            if (image_width, image_height) != (width, height):
                raise PilotBuildError(
                    f"RiceSEG RGB/mask size mismatch for {image_member!r}: "
                    f"RGB={image_width}x{image_height}, mask={width}x{height}"
                )
            stem = Path(image_member).stem
            source_photo = _source_photo_id(stem)
            named_counts = {
                RICESEG_CLASS_NAMES[class_id]: raw_counts[class_id]
                for class_id in sorted(RICESEG_CLASS_NAMES)
            }
            foreground_classes = [
                RICESEG_CLASS_NAMES[class_id]
                for class_id in range(1, 6)
                if raw_counts[class_id] > 0
            ]
            pixel_count = width * height
            weed_pixels = raw_counts[4]
            weed_fraction = weed_pixels / pixel_count if pixel_count else 0.0
            hard_reasons: list[str] = []
            if weed_pixels:
                hard_reasons.append("weed_proposal")
                if weed_fraction < 0.01:
                    hard_reasons.append("small_weed_area")
            if raw_counts[5]:
                hard_reasons.append("duckweed_confuser")
            if raw_counts[2]:
                hard_reasons.append("senescent_rice")
            if raw_counts[3]:
                hard_reasons.append("panicle")
            if len(foreground_classes) >= 3:
                hard_reasons.append("mixed_foreground_classes")
            hardness = (
                5.0 * bool(weed_pixels)
                + 3.0 * bool(raw_counts[5])
                + 1.5 * bool(raw_counts[2])
                + 1.5 * bool(raw_counts[3])
                + len(foreground_classes)
                + 2.0 * bool(weed_pixels and weed_fraction < 0.01)
            )
            site_token = site if site is not None else "unreported_site"
            sample_id = f"riceseg:{country}:{site_token}:{stem}"
            records.append(
                {
                    "sample_id": sample_id,
                    "source_dataset": "RiceSEG",
                    "image_member": image_member,
                    "annotation_member": mask_member,
                    "annotation_format": "indexed_semantic_mask",
                    "width": width,
                    "height": height,
                    "country": country,
                    "site_id": site,
                    "source_photo_id": source_photo,
                    "capture_family": None,
                    "group_id": f"riceseg:{country}:{site_token}:{source_photo}",
                    "group_method": "source_photo_from_tile_filename",
                    "group_confidence": "high",
                    "proposal_class_counts": named_counts,
                    "proposal_annotation_ids": None,
                    "proposal_weed_positive": bool(weed_pixels),
                    "proposal_weed_fraction": weed_fraction,
                    "selection_hardness": round(hardness, 6),
                    "selection_hard_reasons": hard_reasons,
                }
            )

    class_totals: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    sites: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    for record in records:
        class_totals.update(record["proposal_class_counts"])
        countries[record["country"]] += 1
        sites[record["site_id"] if record["site_id"] is not None else "<unreported>"] += 1
        groups[record["group_id"]] += 1
    summary = {
        "image_count": len(records),
        "paired_mask_count": len(records),
        "validated_rgb_mask_pair_count": len(records),
        "source_group_count": len(groups),
        "weed_positive_image_count": sum(record["proposal_weed_positive"] for record in records),
        "country_image_counts": dict(sorted(countries.items())),
        "site_image_counts": dict(sorted(sites.items())),
        "class_pixel_counts": dict(sorted(class_totals.items())),
    }
    return records, summary


def _load_coco_document(
    archive: zipfile.ZipFile,
    members: Mapping[str, zipfile.ZipInfo],
    json_member: str | None,
) -> tuple[str, dict[str, Any]]:
    if json_member is None:
        candidates = sorted(
            name
            for name in members
            if name.casefold().endswith(".json") and "annotation" in Path(name).name.casefold()
        )
        if len(candidates) != 1:
            raise PilotBuildError(
                "Expected exactly one COCO annotation JSON; "
                f"found {len(candidates)} ({candidates[:5]})"
            )
        json_member = candidates[0]
    else:
        json_member = _normalise_member(json_member)
        if json_member not in members:
            raise PilotBuildError(f"COCO JSON member not found: {json_member}")
    info = members[json_member]
    if info.file_size > MAX_JSON_BYTES:
        raise PilotBuildError(
            f"COCO JSON expands to {info.file_size:,} bytes; limit is {MAX_JSON_BYTES:,}"
        )
    with archive.open(info, "r") as stream:
        try:
            document = json.loads(stream.read().decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PilotBuildError(f"Invalid COCO JSON in {json_member}: {exc}") from exc
    if not isinstance(document, dict):
        raise PilotBuildError("COCO root must be a JSON object")
    for field in ("images", "annotations", "categories"):
        if not isinstance(document.get(field), list):
            raise PilotBuildError(f"COCO field {field!r} must be a list")
    return json_member, document


def _roboflow_original_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = ROBOFLOW_LINEAGE_RE.sub("", stem)
    stem = re.sub(r"_(?:jpg|jpeg|png|bmp|tif|tiff)$", "", stem, flags=re.IGNORECASE)
    return stem


def detector_capture_family(filename: str) -> tuple[str, str]:
    """Derive the known capture family and a confidence label from a filename."""
    stem = _roboflow_original_stem(filename)
    lower = stem.casefold()
    patterns = (
        (r"^1a[_-]image", "1a_image"),
        (r"^1b[_-]image", "1b_image"),
        (r"^2[_-]\d+", "2_series"),
        (r"^frame[_-]\d+", "frame"),
        (r"^seedlingcol[_-]03[_-]", "seedlingCol_03"),
        (r"^seedlingcol[_-]04[_-]", "seedlingCol_04"),
        (r"^weeds[_-]seq[_-]", "weeds_seq"),
    )
    for pattern, family in patterns:
        if re.match(pattern, lower):
            return family, "medium"
    if re.fullmatch(r"\d+", stem):
        return "numeric_unresolved", "low"
    token = re.split(r"[_-]?\d", stem, maxsplit=1)[0].strip("_-")
    if token:
        return f"other_{token.casefold()}", "low"
    return "unresolved", "low"


def _resolve_coco_image_member(
    file_name: str,
    json_member: str,
    members: Mapping[str, zipfile.ZipInfo],
) -> str:
    requested = _normalise_member(file_name)
    parent_candidate = str(PurePosixPath(json_member).parent / requested)
    for candidate in (requested, parent_candidate):
        if candidate in members:
            return candidate
    suffix = f"/{requested.casefold()}"
    matches = [name for name in members if name.casefold().endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    raise PilotBuildError(
        f"Could not uniquely resolve COCO image {file_name!r}; matches={matches[:5]}"
    )


def _validate_identifier(value: Any, *, kind: str) -> int | str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise PilotBuildError(f"{kind} id must be an integer or string, got {value!r}")
    return value


def inventory_coco(
    zip_path: Path | str,
    json_member: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Inventory Roboflow-style COCO proposals without extracting the archive."""
    zip_path = Path(zip_path)
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = _zip_member_map(archive)
        json_member, document = _load_coco_document(archive, members, json_member)

        categories: dict[int | str, str] = {}
        for category in document["categories"]:
            if not isinstance(category, dict):
                raise PilotBuildError("Every COCO category must be an object")
            category_id = _validate_identifier(category.get("id"), kind="category")
            name = category.get("name")
            if not isinstance(name, str) or not name.strip():
                raise PilotBuildError(f"COCO category {category_id!r} has no valid name")
            if category_id in categories:
                raise PilotBuildError(f"Duplicate COCO category id: {category_id!r}")
            categories[category_id] = name.strip()

        images: dict[int | str, dict[str, Any]] = {}
        for image in document["images"]:
            if not isinstance(image, dict):
                raise PilotBuildError("Every COCO image must be an object")
            image_id = _validate_identifier(image.get("id"), kind="image")
            if image_id in images:
                raise PilotBuildError(f"Duplicate COCO image id: {image_id!r}")
            file_name = image.get("file_name")
            if not isinstance(file_name, str) or not file_name:
                raise PilotBuildError(f"COCO image {image_id!r} has no file_name")
            images[image_id] = image

        annotations_by_image: dict[int | str, list[dict[str, Any]]] = defaultdict(list)
        annotation_ids: set[int | str] = set()
        for annotation in document["annotations"]:
            if not isinstance(annotation, dict):
                raise PilotBuildError("Every COCO annotation must be an object")
            annotation_id = _validate_identifier(annotation.get("id"), kind="annotation")
            if annotation_id in annotation_ids:
                raise PilotBuildError(f"Duplicate COCO annotation id: {annotation_id!r}")
            annotation_ids.add(annotation_id)
            image_id = _validate_identifier(annotation.get("image_id"), kind="annotation image")
            if image_id not in images:
                raise PilotBuildError(
                    f"COCO annotation {annotation_id!r} references unknown image {image_id!r}"
                )
            category_id = _validate_identifier(
                annotation.get("category_id"), kind="annotation category"
            )
            if category_id not in categories:
                raise PilotBuildError(
                    f"COCO annotation {annotation_id!r} references unknown category {category_id!r}"
                )
            bbox = annotation.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                raise PilotBuildError(f"COCO annotation {annotation_id!r} has invalid bbox")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in bbox
            ):
                raise PilotBuildError(f"COCO annotation {annotation_id!r} has non-finite bbox")
            if bbox[2] <= 0 or bbox[3] <= 0:
                raise PilotBuildError(
                    f"COCO annotation {annotation_id!r} has non-positive bbox size"
                )
            annotations_by_image[image_id].append(annotation)

        for image_id, image in sorted(images.items(), key=lambda item: str(item[0])):
            file_name = image["file_name"]
            image_member = _resolve_coco_image_member(file_name, json_member, members)
            _require_small_member(members[image_member], kind="COCO image")
            width = image.get("width")
            height = image.get("height")
            if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
                raise PilotBuildError(f"COCO image {image_id!r} has invalid width")
            if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
                raise PilotBuildError(f"COCO image {image_id!r} has invalid height")
            actual_width, actual_height = _image_dimensions(
                archive,
                members[image_member],
                kind="COCO image",
            )
            if (actual_width, actual_height) != (width, height):
                raise PilotBuildError(
                    f"COCO image {image_id!r} metadata size {width}x{height} does not match "
                    f"media size {actual_width}x{actual_height}"
                )
            proposals = annotations_by_image.get(image_id, [])
            for annotation in proposals:
                x, y, box_width, box_height = annotation["bbox"]
                if x < 0 or y < 0:
                    raise PilotBuildError(
                        f"COCO annotation {annotation['id']!r} has a negative bbox origin"
                    )
                if x + box_width > width or y + box_height > height:
                    raise PilotBuildError(
                        f"COCO annotation {annotation['id']!r} lies outside image "
                        f"{image_id!r} bounds"
                    )
            class_counts: Counter[str] = Counter(
                categories[item["category_id"]] for item in proposals
            )
            weed_count = sum(
                count
                for name, count in class_counts.items()
                if name.casefold() in {"weed", "weeds"}
            )
            small_count = sum(item["bbox"][2] * item["bbox"][3] < 32 * 32 for item in proposals)
            small_fraction = small_count / len(proposals) if proposals else 0.0
            family, confidence = detector_capture_family(file_name)
            hard_reasons: list[str] = []
            if weed_count:
                hard_reasons.append("weed_proposal")
            if small_fraction >= 0.5 and proposals:
                hard_reasons.append("mostly_small_boxes")
            if len(proposals) >= 50:
                hard_reasons.append("crowded_scene")
            if len(class_counts) >= 2:
                hard_reasons.append("mixed_proposal_classes")
            hardness = (
                5.0 * bool(weed_count)
                + 2.0 * small_fraction
                + min(len(proposals), 100) / 25.0
                + len(class_counts)
            )
            original_stem = _roboflow_original_stem(file_name)
            records.append(
                {
                    "sample_id": f"detector:{image_id}:{Path(file_name).name}",
                    "source_dataset": "rice_detection_for_export",
                    "image_member": image_member,
                    "annotation_member": json_member,
                    "annotation_format": "coco_bounding_box",
                    "width": width,
                    "height": height,
                    "country": None,
                    "site_id": None,
                    "source_photo_id": None,
                    "capture_family": family,
                    "frame_or_image_id": original_stem,
                    "group_id": f"detector:capture_family:{family}",
                    "group_method": "capture_family_from_filename",
                    "group_confidence": confidence,
                    "proposal_class_counts": dict(sorted(class_counts.items())),
                    "proposal_annotation_ids": sorted((item["id"] for item in proposals), key=str),
                    "proposal_weed_positive": bool(weed_count),
                    "proposal_small_box_fraction": round(small_fraction, 8),
                    "selection_hardness": round(hardness, 6),
                    "selection_hard_reasons": hard_reasons,
                }
            )

    category_totals: Counter[str] = Counter()
    families: Counter[str] = Counter()
    for record in records:
        category_totals.update(record["proposal_class_counts"])
        families[record["capture_family"]] += 1
    summary = {
        "image_count": len(records),
        "annotation_count": sum(category_totals.values()),
        "validated_image_count": len(records),
        "weed_positive_image_count": sum(record["proposal_weed_positive"] for record in records),
        "capture_family_count": len(families),
        "capture_family_image_counts": dict(sorted(families.items())),
        "category_annotation_counts": dict(sorted(category_totals.items())),
        "annotation_json_member": json_member,
    }
    return records, summary


def _stable_key(seed: int, *values: object) -> str:
    message = "|".join([str(seed), *(str(value) for value in values)])
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def _round_robin_groups(
    records: Sequence[dict[str, Any]],
    count: int,
    seed: int,
    excluded: set[str] | None = None,
    prior_group_counts: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    excluded = excluded or set()
    prior_group_counts = prior_group_counts or {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["sample_id"] not in excluded:
            groups[record["group_id"]].append(record)
    for group, candidates in groups.items():
        candidates.sort(
            key=lambda record: (
                -float(record["selection_hardness"]),
                _stable_key(seed, group, record["sample_id"]),
            )
        )
    selected: list[dict[str, Any]] = []
    selected_group_counts: Counter[str] = Counter()
    while len(selected) < count:
        active_groups = [group for group, candidates in groups.items() if candidates]
        if not active_groups:
            break
        group = min(
            active_groups,
            key=lambda item: (
                prior_group_counts.get(item, 0) + selected_group_counts[item],
                _stable_key(seed, "group", item),
            ),
        )
        selected.append(groups[group].pop(0))
        selected_group_counts[group] += 1
    return selected


def _select_from_dataset(
    records: Sequence[dict[str, Any]],
    count: int,
    seed: int,
    weed_fraction: float,
) -> list[dict[str, Any]]:
    if count > len(records):
        raise PilotBuildError(f"Requested {count} samples from only {len(records)} records")
    weed_quota = min(
        math.ceil(count * weed_fraction), sum(r["proposal_weed_positive"] for r in records)
    )
    weed_records = [record for record in records if record["proposal_weed_positive"]]
    selected = _round_robin_groups(weed_records, weed_quota, seed)
    selected_ids = {record["sample_id"] for record in selected}
    selected_groups: Counter[str] = Counter(record["group_id"] for record in selected)
    selected.extend(
        _round_robin_groups(
            records,
            count - len(selected),
            seed + 1,
            excluded=selected_ids,
            prior_group_counts=selected_groups,
        )
    )
    if len(selected) != count:
        raise PilotBuildError(f"Selection produced {len(selected)} of {count} requested samples")
    return selected


def select_annotation_pilot(
    riceseg_records: Sequence[dict[str, Any]],
    coco_records: Sequence[dict[str, Any]],
    *,
    target_size: int = DEFAULT_TARGET_SIZE,
    seed: int = DEFAULT_SEED,
    weed_fraction: float = 0.5,
    enforce_public_range: bool = True,
) -> list[dict[str, Any]]:
    """Select an equal-source, weed-biased, group-round-robin pilot."""
    if enforce_public_range and not PUBLIC_MIN_PILOT <= target_size <= PUBLIC_MAX_PILOT:
        raise PilotBuildError(
            f"Pilot size must be {PUBLIC_MIN_PILOT}-{PUBLIC_MAX_PILOT}; got {target_size}"
        )
    if target_size <= 0:
        raise PilotBuildError("Pilot size must be positive")
    if not 0.0 <= weed_fraction <= 1.0:
        raise PilotBuildError("weed_fraction must be between 0 and 1")
    if target_size > len(riceseg_records) + len(coco_records):
        raise PilotBuildError("Pilot size exceeds the combined source inventory")

    riceseg_quota = min(len(riceseg_records), target_size // 2)
    coco_quota = min(len(coco_records), target_size - riceseg_quota)
    remaining = target_size - riceseg_quota - coco_quota
    if remaining:
        add_riceseg = min(remaining, len(riceseg_records) - riceseg_quota)
        riceseg_quota += add_riceseg
        remaining -= add_riceseg
    if remaining:
        coco_quota += min(remaining, len(coco_records) - coco_quota)

    selected = _select_from_dataset(
        riceseg_records, riceseg_quota, seed, weed_fraction
    ) + _select_from_dataset(coco_records, coco_quota, seed + 10_000, weed_fraction)
    selected.sort(key=lambda record: _stable_key(seed, "pilot", record["sample_id"]))
    output: list[dict[str, Any]] = []
    for rank, source in enumerate(selected, start=1):
        record = dict(source)
        record.update(
            {
                "selection_rank": rank,
                "proposal_only": True,
                "review_status": "pending_human_review",
                "reviewer_ids": [],
                "annotation_version": None,
                "positive_weeds": None,
                "verified_empty": None,
                "eligible_for_training": False,
                "eligible_for_evaluation": False,
            }
        )
        output.append(record)
    sample_ids = [record["sample_id"] for record in output]
    if len(sample_ids) != len(set(sample_ids)):
        raise AssertionError("Selection contains duplicate sample IDs")
    return output


def assign_gold_subset(
    samples: list[dict[str, Any]],
    *,
    gold_size: int = DEFAULT_GOLD_SIZE,
    seed: int = DEFAULT_SEED,
    weed_fraction: float = 0.5,
) -> dict[str, Any]:
    """Freeze a deterministic, source-balanced, group-diverse gold subset."""
    if gold_size <= 0 or gold_size > len(samples):
        raise PilotBuildError(f"Gold subset must contain 1-{len(samples)} samples; got {gold_size}")
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        by_source[sample["source_dataset"]].append(sample)
    source_names = sorted(by_source)
    quotas = {name: gold_size // len(source_names) for name in source_names}
    for name in sorted(source_names, key=lambda value: _stable_key(seed, "gold-source", value))[
        : gold_size % len(source_names)
    ]:
        quotas[name] += 1
    if any(quotas[name] > len(by_source[name]) for name in source_names):
        raise PilotBuildError("Gold subset source quota exceeds the selected source inventory")

    gold: list[dict[str, Any]] = []
    for index, name in enumerate(source_names):
        gold.extend(
            _select_from_dataset(
                by_source[name],
                quotas[name],
                seed + 20_000 + index,
                weed_fraction,
            )
        )
    gold_ids = {sample["sample_id"] for sample in gold}
    for sample in samples:
        sample["gold_subset"] = sample["sample_id"] in gold_ids
        sample["gold_annotation_contract"] = (
            "two_independent_annotators_then_adjudication" if sample["gold_subset"] else None
        )
    ordered_ids = sorted(gold_ids)
    membership_hash = hashlib.sha256(("\n".join(ordered_ids) + "\n").encode("utf-8")).hexdigest()
    return {
        "size": len(ordered_ids),
        "source_counts": dict(sorted(Counter(sample["source_dataset"] for sample in gold).items())),
        "proposal_weed_positive_count": sum(sample["proposal_weed_positive"] for sample in gold),
        "distinct_group_count": len({sample["group_id"] for sample in gold}),
        "membership_sha256": membership_hash,
        "sample_ids": ordered_ids,
    }


def populate_selected_lineage_and_hashes(
    samples: list[dict[str, Any]],
    *,
    riceseg_zip: Path | str,
    coco_zip: Path | str,
) -> None:
    """Attach per-image identity and explicit-null lineage to selected rows only."""
    with (
        zipfile.ZipFile(riceseg_zip, "r") as rice_archive,
        zipfile.ZipFile(coco_zip, "r") as coco_archive,
    ):
        archives = {
            "RiceSEG": rice_archive,
            "rice_detection_for_export": coco_archive,
        }
        member_maps = {name: _zip_member_map(archive) for name, archive in archives.items()}
        seen_hashes: dict[str, str] = {}
        for sample in samples:
            dataset_id = sample["source_dataset"]
            archive = archives[dataset_id]
            member = sample["image_member"]
            info = member_maps[dataset_id].get(member)
            if info is None:
                raise PilotBuildError(f"Selected image member disappeared from archive: {member}")
            image_sha256 = _sha256_zip_member(archive, info)
            if image_sha256 in seen_hashes:
                raise PilotBuildError(
                    f"Selected samples {seen_hashes[image_sha256]!r} and {sample['sample_id']!r} "
                    "contain identical image bytes"
                )
            seen_hashes[image_sha256] = sample["sample_id"]
            sample.update(
                {
                    "dataset_id": dataset_id,
                    "dataset_version": (
                        "received-2026-07-13" if dataset_id == "RiceSEG" else "received-2026-07-20"
                    ),
                    "image_uri": member,
                    "source_image_sha256": image_sha256,
                    "field_id": None,
                    "session_id": None,
                    "capture_pass_id": None,
                    "frame_id": sample.get("frame_or_image_id"),
                    "split": "unassigned",
                    "capture_metadata": {
                        "group_method": sample["group_method"],
                        "group_confidence": sample["group_confidence"],
                    },
                    "annotator_id": None,
                    "reviewer_id": None,
                    "guide_version": "v1",
                }
            )


def annotation_record_stub(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Create an unreviewed, manual-first JSONL intake row from one pilot sample."""
    return {
        "schema_version": "agrinav.annotation_record.v1",
        "record_id": sample["sample_id"],
        "image_id": sample["sample_id"],
        "source": {
            "dataset_id": sample["dataset_id"],
            "dataset_version": sample["dataset_version"],
            "image_uri": sample["image_uri"],
            "source_image_sha256": sample["source_image_sha256"],
            "width": sample["width"],
            "height": sample["height"],
            "country": sample.get("country"),
            "site_id": sample.get("site_id"),
            "field_id": sample.get("field_id"),
            "session_id": sample.get("session_id"),
            "capture_pass_id": sample.get("capture_pass_id"),
            "frame_id": sample.get("frame_id"),
            "source_photo_id": sample.get("source_photo_id"),
            "group_id": sample["group_id"],
            "split": "unassigned",
            "capture_metadata": {
                **sample.get("capture_metadata", {}),
                "pilot_selection_rank": sample["selection_rank"],
                "gold_subset": sample["gold_subset"],
            },
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
            "annotator_id": None,
            "annotator_completed_at": None,
            "reviewer_id": None,
            "reviewed_at": None,
            "review_status": "unreviewed",
            "annotation_version": None,
            "guide_version": "v1",
        },
        "verified_empty": None,
        "unusable": False,
        "annotations": [],
    }


def _safe_materialized_name(rank: int, member: str) -> str:
    basename = Path(member).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    if not safe:
        safe = "media.bin"
    return f"{rank:04d}_{safe}"


def _copy_zip_member(
    archive: zipfile.ZipFile,
    member: str,
    destination: Path,
    *,
    overwrite: bool,
) -> None:
    info = archive.getinfo(member)
    _require_small_member(info, kind="materialized media")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise PilotBuildError(f"Refusing to overwrite existing media: {destination}")
    with archive.open(info, "r") as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def materialize_selected_media(
    samples: list[dict[str, Any]],
    *,
    riceseg_zip: Path | str,
    coco_zip: Path | str,
    output_dir: Path | str,
    overwrite: bool = False,
) -> None:
    """Copy only selected images and RiceSEG masks into an explicit directory."""
    output_dir = Path(output_dir)
    with (
        zipfile.ZipFile(riceseg_zip, "r") as rice_archive,
        zipfile.ZipFile(coco_zip, "r") as coco_archive,
    ):
        for record in samples:
            source_name = "riceseg" if record["source_dataset"] == "RiceSEG" else "detector"
            archive = rice_archive if source_name == "riceseg" else coco_archive
            image_path = (
                output_dir
                / source_name
                / "images"
                / _safe_materialized_name(record["selection_rank"], record["image_member"])
            )
            _copy_zip_member(archive, record["image_member"], image_path, overwrite=overwrite)
            record["materialized_image_path"] = str(image_path.resolve())
            record["materialized_annotation_path"] = None
            if source_name == "riceseg":
                mask_path = (
                    output_dir
                    / source_name
                    / "masks"
                    / _safe_materialized_name(record["selection_rank"], record["annotation_member"])
                )
                _copy_zip_member(
                    archive, record["annotation_member"], mask_path, overwrite=overwrite
                )
                record["materialized_annotation_path"] = str(mask_path.resolve())


def load_pilot_config(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotBuildError(f"Could not load pilot config {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PilotBuildError(f"Pilot config {path} must contain a JSON object")
    for key in ("total_images", "gold_images"):
        value = document.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PilotBuildError(f"Pilot config field {key!r} must be a positive integer")
    sampling = document.get("sampling_targets")
    if not isinstance(sampling, dict):
        raise PilotBuildError("Pilot config sampling_targets must be an object")
    weed_fraction = sampling.get("weed_positive_fraction_min")
    if (
        not isinstance(weed_fraction, (int, float))
        or isinstance(weed_fraction, bool)
        or not math.isfinite(weed_fraction)
    ):
        raise PilotBuildError("Pilot config weed_positive_fraction_min must be numeric")
    if not 0.0 <= float(weed_fraction) <= 1.0:
        raise PilotBuildError("Pilot config weed_positive_fraction_min must be between 0 and 1")
    return document


def build_manifest(
    *,
    riceseg_zip: Path | str,
    coco_zip: Path | str,
    target_size: int = DEFAULT_TARGET_SIZE,
    gold_size: int | None = None,
    seed: int = DEFAULT_SEED,
    weed_fraction: float = 0.5,
    coco_json_member: str | None = None,
    enforce_public_range: bool = True,
    pilot_config_path: Path | str | None = None,
) -> dict[str, Any]:
    riceseg_zip = Path(riceseg_zip).resolve()
    coco_zip = Path(coco_zip).resolve()
    riceseg_records, riceseg_summary = inventory_riceseg(riceseg_zip)
    coco_records, coco_summary = inventory_coco(coco_zip, json_member=coco_json_member)
    samples = select_annotation_pilot(
        riceseg_records,
        coco_records,
        target_size=target_size,
        seed=seed,
        weed_fraction=weed_fraction,
        enforce_public_range=enforce_public_range,
    )
    resolved_gold_size = min(DEFAULT_GOLD_SIZE, target_size) if gold_size is None else gold_size
    populate_selected_lineage_and_hashes(
        samples,
        riceseg_zip=riceseg_zip,
        coco_zip=coco_zip,
    )
    gold_summary = assign_gold_subset(
        samples,
        gold_size=resolved_gold_size,
        seed=seed,
        weed_fraction=weed_fraction,
    )
    selected_source_counts = Counter(sample["source_dataset"] for sample in samples)
    proposal_weed_positive_count = sum(sample["proposal_weed_positive"] for sample in samples)
    proposal_hard_flagged_count = sum(bool(sample["selection_hard_reasons"]) for sample in samples)
    selected_group_counts = Counter(sample["group_id"] for sample in samples)
    pilot_config = None
    if pilot_config_path is not None:
        config_path = Path(pilot_config_path).resolve()
        config_document = load_pilot_config(config_path)
        pilot_config = {
            "path": str(config_path),
            "sha256": sha256_file(config_path),
            "requested_sampling_targets": config_document["sampling_targets"],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "scripts/build_annotation_pilot.py",
        "pilot_config": pilot_config,
        "selection": {
            "target_size": target_size,
            "selected_size": len(samples),
            "seed": seed,
            "weed_positive_target_fraction_per_source": weed_fraction,
            "policy": "equal-source allocation, weed-positive quota, hardness ranking, group round-robin",
            "observed_proposal_only": {
                "source_counts": dict(sorted(selected_source_counts.items())),
                "weed_positive_count": proposal_weed_positive_count,
                "weed_positive_fraction": proposal_weed_positive_count / len(samples),
                "hard_flagged_count": proposal_hard_flagged_count,
                "hard_flagged_fraction": proposal_hard_flagged_count / len(samples),
                "distinct_group_count": len(selected_group_counts),
                "max_samples_in_one_provisional_group": max(selected_group_counts.values()),
                "verified_negative_or_nonactionable_count": None,
            },
            "quota_warning": (
                "Weed-positive and hard-condition values are proposal heuristics, not ground truth. "
                "The verified-negative/nonactionable quota cannot be evaluated until full-image human review."
            ),
            "gold_subset": gold_summary,
        },
        "review_contract": {
            "upstream_annotations_are_proposals_only": True,
            "no_proposal_does_not_mean_verified_empty": True,
            "human_review_required_for_training": True,
            "human_review_required_for_evaluation": True,
        },
        "sources": {
            "RiceSEG": {
                "archive_path": str(riceseg_zip),
                "archive_sha256": sha256_file(riceseg_zip),
                "inventory": riceseg_summary,
                "mask_class_ids": {str(key): value for key, value in RICESEG_CLASS_NAMES.items()},
            },
            "rice_detection_for_export": {
                "archive_path": str(coco_zip),
                "archive_sha256": sha256_file(coco_zip),
                "inventory": coco_summary,
            },
        },
        "samples": samples,
    }


def _write_text_atomic(payload: str, path: Path, *, overwrite: bool, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise PilotBuildError(f"Refusing to overwrite existing {kind}: {path}")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_manifest(
    manifest: Mapping[str, Any], path: Path | str, *, overwrite: bool = False
) -> None:
    path = Path(path)
    payload = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _write_text_atomic(payload, path, overwrite=overwrite, kind="manifest")


def write_annotation_stubs(
    samples: Sequence[Mapping[str, Any]],
    path: Path | str,
    *,
    overwrite: bool = False,
) -> None:
    path = Path(path)
    payload = "".join(
        json.dumps(annotation_record_stub(sample), sort_keys=True, ensure_ascii=False) + "\n"
        for sample in samples
    )
    _write_text_atomic(payload, path, overwrite=overwrite, kind="annotation intake JSONL")


def _preflight_output(path: Path | None, *, overwrite: bool, kind: str) -> None:
    if path is not None and path.exists() and not overwrite:
        raise PilotBuildError(f"Refusing to overwrite existing {kind}: {path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--riceseg-zip", required=True, type=Path)
    parser.add_argument("--coco-zip", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--output-annotation-jsonl", type=Path)
    parser.add_argument("--config", type=Path, help="Optional annotation pilot JSON config")
    parser.add_argument("--target-size", type=int)
    parser.add_argument("--gold-size", type=int)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--weed-fraction", type=float)
    parser.add_argument("--coco-json-member")
    parser.add_argument(
        "--materialize-dir",
        type=Path,
        help="Optional destination for selected media only; raw ZIPs remain untouched.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        config = load_pilot_config(args.config) if args.config is not None else None
        target_size = (
            args.target_size
            if args.target_size is not None
            else config["total_images"] if config is not None else DEFAULT_TARGET_SIZE
        )
        gold_size = (
            args.gold_size
            if args.gold_size is not None
            else config["gold_images"] if config is not None else DEFAULT_GOLD_SIZE
        )
        weed_fraction = (
            args.weed_fraction
            if args.weed_fraction is not None
            else (
                float(config["sampling_targets"]["weed_positive_fraction_min"])
                if config is not None
                else 0.5
            )
        )
        _preflight_output(args.output_manifest, overwrite=args.overwrite, kind="manifest")
        _preflight_output(
            args.output_annotation_jsonl,
            overwrite=args.overwrite,
            kind="annotation intake JSONL",
        )
        manifest = build_manifest(
            riceseg_zip=args.riceseg_zip,
            coco_zip=args.coco_zip,
            target_size=target_size,
            gold_size=gold_size,
            seed=args.seed,
            weed_fraction=weed_fraction,
            coco_json_member=args.coco_json_member,
            pilot_config_path=args.config,
        )
        if args.materialize_dir is not None:
            materialize_selected_media(
                manifest["samples"],
                riceseg_zip=args.riceseg_zip,
                coco_zip=args.coco_zip,
                output_dir=args.materialize_dir,
                overwrite=args.overwrite,
            )
        write_manifest(manifest, args.output_manifest, overwrite=args.overwrite)
        if args.output_annotation_jsonl is not None:
            write_annotation_stubs(
                manifest["samples"],
                args.output_annotation_jsonl,
                overwrite=args.overwrite,
            )
    except (OSError, zipfile.BadZipFile, PilotBuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    selected = manifest["samples"]
    weed_positive = sum(record["proposal_weed_positive"] for record in selected)
    print(f"Wrote {len(selected)} proposal-only samples to {args.output_manifest}")
    print(f"Frozen gold subset: {manifest['selection']['gold_subset']['size']}/{len(selected)}")
    print(f"Proposal weed-positive: {weed_positive}/{len(selected)}")
    print("Human review is required; verified_empty remains null for every sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
