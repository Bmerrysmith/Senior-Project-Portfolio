#!/usr/bin/env python3
"""Validate AgriNav JSONL annotation packages using only the Python stdlib.

The JSON Schema in ``data/schemas/annotation_record.v1.schema.json`` documents
the wire format.  This module deliberately implements the safety-critical
checks itself so validation does not depend on the optional ``jsonschema``
package.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "agrinav.annotation_record.v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REVIEW_STATUSES = {
    "unreviewed",
    "in_review",
    "changes_requested",
    "accepted",
    "adjudicated",
    "rejected_unusable",
}
ACCEPTED_STATUSES = {"accepted", "adjudicated"}
MODEL_METHODS = {"model_assisted", "model_silence"}
HUMAN_EDIT_STATES = {
    "unreviewed",
    "accepted_unchanged",
    "edited",
    "replaced",
    "human_only",
}
SPLITS = {"train", "validation", "test", "challenge", "ood", "unassigned"}
KNOWN_GEOMETRY_TYPES = {"bbox", "polygon", "instance_mask", "semantic_mask"}
OCCLUSION_VALUES = {"none", "partial", "severe", "unknown"}
ANNOTATION_CONFIDENCE_VALUES = {"certain", "probable", "uncertain"}
HUMAN_EDIT_ACTIONS = {
    "accepted",
    "edited",
    "deleted",
    "added",
    "reclassified",
    "split",
    "merged",
}
OBJECT_ATTRIBUTE_KEYS = (
    "source_object_id",
    "species",
    "growth_stage",
    "occlusion",
    "truncated",
    "annotation_confidence",
    "treatment_eligible",
    "human_edit_action",
)
OntologyEntry = tuple[str, str, frozenset[str]]


class AnnotationValidationError(ValueError):
    """Raised when an annotation package violates its contract."""


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _require_mapping(value: Any, path: str, errors: list[str]) -> Mapping[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return None
    return value


def _require_keys(
    value: Mapping[str, Any], keys: Iterable[str], path: str, errors: list[str]
) -> None:
    for key in keys:
        if key not in value:
            errors.append(f"{path}.{key}: missing required field (use explicit null when unknown)")


def _reject_unexpected(
    value: Mapping[str, Any],
    allowed: Iterable[str],
    path: str,
    errors: list[str],
) -> None:
    for key in sorted(set(value) - set(allowed)):
        errors.append(f"{path}.{key}: unexpected field for annotation_record.v1")


def _nullable_string(value: Any, path: str, errors: list[str]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        errors.append(f"{path}: must be a non-empty string or null")


def load_ontology(path: Path | str) -> dict[str, OntologyEntry]:
    """Return canonical label -> (biological class, decision role, geometry types)."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnnotationValidationError(f"Could not load ontology {path}: {exc}") from exc
    labels = document.get("canonical_labels") if isinstance(document, dict) else None
    if not isinstance(labels, list) or not labels:
        raise AnnotationValidationError(f"Ontology {path} has no canonical_labels list")
    result: dict[str, OntologyEntry] = {}
    for index, item in enumerate(labels):
        if not isinstance(item, dict):
            raise AnnotationValidationError(f"Ontology canonical_labels[{index}] is not an object")
        values = (item.get("name"), item.get("biological_class"), item.get("decision_role"))
        if not all(isinstance(value, str) and value for value in values):
            raise AnnotationValidationError(f"Ontology canonical_labels[{index}] has invalid names")
        geometry = item.get("geometry")
        if (
            not isinstance(geometry, list)
            or not geometry
            or any(
                not isinstance(value, str) or value not in KNOWN_GEOMETRY_TYPES
                for value in geometry
            )
        ):
            raise AnnotationValidationError(
                f"Ontology canonical_labels[{index}] has invalid or empty geometry list"
            )
        if values[0] in result:
            raise AnnotationValidationError(f"Ontology has duplicate label {values[0]!r}")
        result[values[0]] = (values[1], values[2], frozenset(geometry))
    return result


def _validate_object_attributes(
    attributes: Any,
    path: str,
    errors: list[str],
) -> tuple[str | None, str | None]:
    """Validate required object metadata and return (edit action, source object ID)."""
    value = _require_mapping(attributes, path, errors)
    if value is None:
        return None, None
    _require_keys(value, OBJECT_ATTRIBUTE_KEYS, path, errors)
    unexpected = sorted(set(value) - set(OBJECT_ATTRIBUTE_KEYS))
    for field in unexpected:
        errors.append(f"{path}.{field}: field is not part of annotation_record.v1")
    for field in ("source_object_id", "species", "growth_stage"):
        _nullable_string(value.get(field), f"{path}.{field}", errors)
    if value.get("occlusion") not in OCCLUSION_VALUES:
        errors.append(f"{path}.occlusion: must be one of {sorted(OCCLUSION_VALUES)}")
    if not isinstance(value.get("truncated"), bool):
        errors.append(f"{path}.truncated: must be boolean")
    if value.get("annotation_confidence") not in ANNOTATION_CONFIDENCE_VALUES:
        errors.append(
            f"{path}.annotation_confidence: must be one of "
            f"{sorted(ANNOTATION_CONFIDENCE_VALUES)}"
        )
    treatment_eligible = value.get("treatment_eligible")
    if treatment_eligible is not None and not isinstance(treatment_eligible, bool):
        errors.append(f"{path}.treatment_eligible: must be boolean or null")
    action = value.get("human_edit_action")
    if action is not None and action not in HUMAN_EDIT_ACTIONS:
        errors.append(
            f"{path}.human_edit_action: must be one of {sorted(HUMAN_EDIT_ACTIONS)} or null"
        )
        action = None
    source_object_id = value.get("source_object_id")
    if not isinstance(source_object_id, str) or not source_object_id.strip():
        source_object_id = None
    if action in HUMAN_EDIT_ACTIONS - {"added"} and source_object_id is None:
        errors.append(f"{path}.source_object_id: required for human_edit_action={action!r}")
    return action, source_object_id


def _validate_bbox(bbox: Any, width: int, height: int, path: str, errors: list[str]) -> None:
    if not isinstance(bbox, list) or len(bbox) != 4 or not all(_is_number(v) for v in bbox):
        errors.append(f"{path}: bbox must be four finite numbers [x, y, width, height]")
        return
    x, y, box_width, box_height = bbox
    if x < 0 or y < 0 or box_width <= 0 or box_height <= 0:
        errors.append(f"{path}: bbox must have non-negative origin and positive size")
    if x + box_width > width or y + box_height > height:
        errors.append(f"{path}: bbox lies outside {width}x{height} image bounds")


def _validate_polygon(polygon: Any, width: int, height: int, path: str, errors: list[str]) -> None:
    if not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2:
        errors.append(f"{path}: polygon must contain at least three [x, y] points")
        return
    if not all(_is_number(v) for v in polygon):
        errors.append(f"{path}: polygon coordinates must be finite numbers")
        return
    points = list(zip(polygon[0::2], polygon[1::2]))
    if any(x < 0 or y < 0 or x > width or y > height for x, y in points):
        errors.append(f"{path}: polygon lies outside {width}x{height} image bounds")
    area2 = abs(
        sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))
    )
    if area2 == 0:
        errors.append(f"{path}: polygon has zero area")


def _validate_rle(rle: Any, width: int, height: int, path: str, errors: list[str]) -> None:
    value = _require_mapping(rle, path, errors)
    if value is None:
        return
    _require_keys(value, ("size", "counts"), path, errors)
    _reject_unexpected(value, ("size", "counts"), path, errors)
    size = value.get("size")
    if size != [height, width]:
        errors.append(f"{path}.size: must equal image [height, width] = [{height}, {width}]")
    counts = value.get("counts")
    decoded_counts: list[int] | None = None
    if isinstance(counts, list):
        if not counts or any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts
        ):
            errors.append(
                f"{path}.counts: uncompressed RLE must be non-empty non-negative integers"
            )
        else:
            decoded_counts = counts
    elif isinstance(counts, str) and counts:
        try:
            decoded_counts = _decode_coco_compressed_rle(counts)
        except ValueError as exc:
            errors.append(f"{path}.counts: invalid compressed COCO RLE ({exc})")
    else:
        errors.append(f"{path}.counts: must be a non-empty COCO RLE string or integer list")
    if decoded_counts is not None:
        if sum(decoded_counts) != width * height:
            errors.append(f"{path}.counts: RLE must cover exactly width*height pixels")
        elif sum(decoded_counts[1::2]) <= 0:
            errors.append(f"{path}.counts: mask is empty")


def _decode_coco_compressed_rle(encoded: str) -> list[int]:
    """Decode the compact COCO run-count string without materialising a mask."""
    counts: list[int] = []
    position = 0
    while position < len(encoded):
        value = 0
        shift = 0
        more = True
        while more:
            if position >= len(encoded):
                raise ValueError("truncated run")
            code = ord(encoded[position]) - 48
            position += 1
            if code < 0 or code > 0x3F:
                raise ValueError("character outside COCO encoding range")
            value |= (code & 0x1F) << (5 * shift)
            more = bool(code & 0x20)
            if not more and (code & 0x10):
                value |= -1 << (5 * (shift + 1))
            shift += 1
            if shift > 13:
                raise ValueError("run value is too long")
        if len(counts) > 2:
            value += counts[-2]
        if value < 0:
            raise ValueError("negative run length")
        counts.append(value)
    if not counts:
        raise ValueError("no runs")
    return counts


def _validate_geometry(
    geometry: Any, width: int, height: int, path: str, errors: list[str]
) -> None:
    value = _require_mapping(geometry, path, errors)
    if value is None:
        return
    _require_keys(value, ("type",), path, errors)
    geometry_type = value.get("type")
    if geometry_type == "bbox":
        _require_keys(value, ("bbox",), path, errors)
        _reject_unexpected(value, ("type", "bbox"), path, errors)
        _validate_bbox(value.get("bbox"), width, height, f"{path}.bbox", errors)
    elif geometry_type == "polygon":
        _require_keys(value, ("polygon",), path, errors)
        _reject_unexpected(value, ("type", "polygon"), path, errors)
        _validate_polygon(value.get("polygon"), width, height, f"{path}.polygon", errors)
    elif geometry_type in {"instance_mask", "semantic_mask"}:
        _require_keys(value, ("rle",), path, errors)
        _reject_unexpected(value, ("type", "rle"), path, errors)
        _validate_rle(value.get("rle"), width, height, f"{path}.rle", errors)
    else:
        errors.append(f"{path}.type: must be bbox, polygon, instance_mask, or semantic_mask")


def validate_record(
    record: Any,
    ontology: Mapping[str, OntologyEntry],
    *,
    location: str = "record",
) -> list[str]:
    """Return all validation errors for one annotation record."""
    errors: list[str] = []
    value = _require_mapping(record, location, errors)
    if value is None:
        return errors
    required = (
        "schema_version",
        "record_id",
        "image_id",
        "source",
        "provenance",
        "review",
        "verified_empty",
        "unusable",
        "annotations",
    )
    _require_keys(value, required, location, errors)
    _reject_unexpected(value, required, location, errors)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{location}.schema_version: must be {SCHEMA_VERSION!r}")
    for field in ("record_id", "image_id"):
        if not isinstance(value.get(field), str) or not value.get(field, "").strip():
            errors.append(f"{location}.{field}: must be a non-empty string")

    source = _require_mapping(value.get("source"), f"{location}.source", errors)
    width = height = 0
    if source is not None:
        source_keys = (
            "dataset_id",
            "dataset_version",
            "image_uri",
            "source_image_sha256",
            "width",
            "height",
            "country",
            "site_id",
            "field_id",
            "session_id",
            "capture_pass_id",
            "frame_id",
            "source_photo_id",
            "group_id",
            "split",
            "capture_metadata",
        )
        _require_keys(source, source_keys, f"{location}.source", errors)
        _reject_unexpected(source, source_keys, f"{location}.source", errors)
        for field in ("dataset_id", "image_uri", "group_id"):
            if not isinstance(source.get(field), str) or not source.get(field, "").strip():
                errors.append(f"{location}.source.{field}: must be a non-empty string")
        digest = source.get("source_image_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append(
                f"{location}.source.source_image_sha256: must be 64 hexadecimal characters"
            )
        width, height = source.get("width"), source.get("height")
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            errors.append(f"{location}.source.width: must be a positive integer")
            width = 0
        if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
            errors.append(f"{location}.source.height: must be a positive integer")
            height = 0
        for field in (
            "dataset_version",
            "country",
            "site_id",
            "field_id",
            "session_id",
            "capture_pass_id",
            "frame_id",
            "source_photo_id",
        ):
            _nullable_string(source.get(field), f"{location}.source.{field}", errors)
        if source.get("split") not in SPLITS:
            errors.append(f"{location}.source.split: must be one of {sorted(SPLITS)}")
        if source.get("capture_metadata") is not None and not isinstance(
            source.get("capture_metadata"), dict
        ):
            errors.append(f"{location}.source.capture_metadata: must be an object or null")

    provenance = _require_mapping(value.get("provenance"), f"{location}.provenance", errors)
    method = model_id = human_edit_state = None
    if provenance is not None:
        provenance_keys = (
            "proposal_model_id",
            "proposal_model_revision",
            "proposal_method",
            "prompt",
            "thresholds",
            "generated_at",
            "original_proposal",
            "human_edit_state",
        )
        _require_keys(provenance, provenance_keys, f"{location}.provenance", errors)
        _reject_unexpected(provenance, provenance_keys, f"{location}.provenance", errors)
        for field in ("proposal_model_id", "proposal_model_revision", "prompt", "generated_at"):
            _nullable_string(provenance.get(field), f"{location}.provenance.{field}", errors)
        model_id = provenance.get("proposal_model_id")
        method = provenance.get("proposal_method")
        if method not in {"manual", "imported", "model_assisted", "model_silence"}:
            errors.append(f"{location}.provenance.proposal_method: invalid method")
        if provenance.get("thresholds") is not None and not isinstance(
            provenance.get("thresholds"), dict
        ):
            errors.append(f"{location}.provenance.thresholds: must be an object or null")
        original_proposal = provenance.get("original_proposal")
        if original_proposal is not None and not isinstance(original_proposal, (dict, list)):
            errors.append(
                f"{location}.provenance.original_proposal: must be an object, array, or null"
            )
        human_edit_state = provenance.get("human_edit_state")
        if human_edit_state not in HUMAN_EDIT_STATES:
            errors.append(f"{location}.provenance.human_edit_state: invalid edit state")
        if method in MODEL_METHODS and model_id is None:
            errors.append(
                f"{location}.provenance.proposal_model_id: required for model-derived records"
            )
        if method in MODEL_METHODS:
            for field in ("proposal_model_revision", "prompt", "generated_at"):
                if provenance.get(field) is None:
                    errors.append(
                        f"{location}.provenance.{field}: required for model-derived records"
                    )
            thresholds = provenance.get("thresholds")
            if not isinstance(thresholds, dict) or not thresholds:
                errors.append(
                    f"{location}.provenance.thresholds: model-derived records require a non-empty object"
                )
            if original_proposal is None:
                errors.append(
                    f"{location}.provenance.original_proposal: model-derived records must preserve raw output"
                )
        if method == "imported" and original_proposal is None:
            errors.append(
                f"{location}.provenance.original_proposal: imported records must preserve raw source objects"
            )
        if method == "manual":
            proposal_fields = (
                "proposal_model_id",
                "proposal_model_revision",
                "prompt",
                "thresholds",
                "generated_at",
                "original_proposal",
            )
            if any(provenance.get(field) is not None for field in proposal_fields):
                errors.append(
                    f"{location}.provenance: manual records must use explicit null proposal/model fields"
                )
            if human_edit_state != "human_only":
                errors.append(
                    f"{location}.provenance.human_edit_state: manual records must use 'human_only'"
                )

    review = _require_mapping(value.get("review"), f"{location}.review", errors)
    review_status = reviewer_id = None
    if review is not None:
        review_keys = (
            "annotator_id",
            "annotator_completed_at",
            "reviewer_id",
            "reviewed_at",
            "review_status",
            "annotation_version",
            "guide_version",
        )
        _require_keys(review, review_keys, f"{location}.review", errors)
        _reject_unexpected(review, review_keys, f"{location}.review", errors)
        for field in (
            "annotator_id",
            "annotator_completed_at",
            "reviewer_id",
            "reviewed_at",
            "annotation_version",
            "guide_version",
        ):
            _nullable_string(review.get(field), f"{location}.review.{field}", errors)
        review_status = review.get("review_status")
        reviewer_id = review.get("reviewer_id")
        if review_status not in REVIEW_STATUSES:
            errors.append(f"{location}.review.review_status: invalid status")
        if (
            review_status in ACCEPTED_STATUSES
            and (method in MODEL_METHODS or model_id is not None)
            and reviewer_id is None
        ):
            errors.append(
                f"{location}.review.reviewer_id: accepted model-assisted records require a human reviewer"
            )
        if review_status in ACCEPTED_STATUSES:
            for field in (
                "annotator_id",
                "annotator_completed_at",
                "annotation_version",
                "guide_version",
            ):
                if review.get(field) is None:
                    errors.append(f"{location}.review.{field}: required for accepted records")
            if reviewer_id is not None and review.get("reviewed_at") is None:
                errors.append(
                    f"{location}.review.reviewed_at: required when reviewer_id is present"
                )
            if method in MODEL_METHODS and human_edit_state == "unreviewed":
                errors.append(
                    f"{location}.provenance.human_edit_state: accepted model-derived records cannot be unreviewed"
                )

    verified_empty = value.get("verified_empty")
    if verified_empty is not None and not isinstance(verified_empty, bool):
        errors.append(f"{location}.verified_empty: must be boolean or null")
    unusable = value.get("unusable")
    if not isinstance(unusable, bool):
        errors.append(f"{location}.unusable: must be boolean")
        unusable = False
    if unusable:
        if verified_empty is not None:
            errors.append(
                f"{location}.verified_empty: unusable images must remain unverified (null)"
            )
        if review_status in ACCEPTED_STATUSES:
            errors.append(
                f"{location}.review.review_status: unusable images cannot be accepted/adjudicated"
            )
    if review_status == "rejected_unusable":
        if not unusable:
            errors.append(f"{location}.unusable: rejected_unusable review requires unusable=true")
        if verified_empty is not None:
            errors.append(f"{location}.verified_empty: rejected_unusable images must remain null")

    annotations = value.get("annotations")
    if not isinstance(annotations, list):
        errors.append(f"{location}.annotations: must be an array")
        annotations = []
    annotation_ids: set[str] = set()
    has_weed_target = False
    for index, annotation in enumerate(annotations):
        path = f"{location}.annotations[{index}]"
        item = _require_mapping(annotation, path, errors)
        if item is None:
            continue
        annotation_keys = (
            "annotation_id",
            "label",
            "biological_class",
            "decision_role",
            "geometry",
            "attributes",
        )
        _require_keys(item, annotation_keys, path, errors)
        _reject_unexpected(item, annotation_keys, path, errors)
        annotation_id = item.get("annotation_id")
        if not isinstance(annotation_id, str) or not annotation_id.strip():
            errors.append(f"{path}.annotation_id: must be a non-empty string")
        elif annotation_id in annotation_ids:
            errors.append(
                f"{path}.annotation_id: duplicate annotation ID {annotation_id!r} within record"
            )
        else:
            annotation_ids.add(annotation_id)
        label = item.get("label")
        expected = ontology.get(label) if isinstance(label, str) else None
        if expected is None:
            errors.append(f"{path}.label: unknown canonical label {label!r}")
        elif (item.get("biological_class"), item.get("decision_role")) != expected[:2]:
            errors.append(
                f"{path}: label {label!r} requires biological_class={expected[0]!r} "
                f"and decision_role={expected[1]!r}"
            )
        edit_action, _ = _validate_object_attributes(
            item.get("attributes"), f"{path}.attributes", errors
        )
        attributes = item.get("attributes")
        if (
            review_status in ACCEPTED_STATUSES
            and isinstance(attributes, dict)
            and attributes.get("treatment_eligible") is not None
            and reviewer_id is None
        ):
            errors.append(
                f"{path}.attributes.treatment_eligible: a non-null decision requires an independent reviewer"
            )
        if review_status in ACCEPTED_STATUSES and edit_action is None:
            errors.append(
                f"{path}.attributes.human_edit_action: required for accepted/adjudicated records"
            )
        if label == "weed_target" and edit_action != "deleted":
            has_weed_target = True
        if width > 0 and height > 0:
            _validate_geometry(item.get("geometry"), width, height, f"{path}.geometry", errors)
        geometry = item.get("geometry")
        geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
        if (
            expected is not None
            and review_status in ACCEPTED_STATUSES
            and edit_action != "deleted"
            and geometry_type not in expected[2]
        ):
            errors.append(
                f"{path}.geometry.type: accepted label {label!r} requires one of "
                f"{sorted(expected[2])}, not {geometry_type!r}"
            )

    if verified_empty is True:
        if has_weed_target:
            errors.append(
                f"{location}.verified_empty: cannot coexist with a weed_target annotation"
            )
        if review_status not in ACCEPTED_STATUSES or reviewer_id is None:
            errors.append(
                f"{location}.verified_empty: requires accepted/adjudicated full-image human review"
            )
        if method == "model_silence" and human_edit_state in {"unreviewed", "accepted_unchanged"}:
            errors.append(
                f"{location}.verified_empty: model silence cannot establish a verified empty"
            )
    elif verified_empty is False:
        if not has_weed_target:
            errors.append(
                f"{location}.verified_empty: false requires at least one non-deleted weed_target annotation"
            )
        if review_status not in ACCEPTED_STATUSES:
            errors.append(
                f"{location}.verified_empty: false requires accepted/adjudicated human annotation"
            )
    return errors


def read_jsonl(path: Path | str) -> list[tuple[int, Any]]:
    path = Path(path)
    rows: list[tuple[int, Any]] = []
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append((line_number, json.loads(line)))
                except json.JSONDecodeError as exc:
                    raise AnnotationValidationError(
                        f"{path}:{line_number}: invalid JSON: {exc}"
                    ) from exc
    except OSError as exc:
        raise AnnotationValidationError(f"Could not read {path}: {exc}") from exc
    if not rows:
        raise AnnotationValidationError(f"{path}: package contains no records")
    return rows


def _group_split_pairs(document: Any) -> Iterable[tuple[str, str]]:
    if isinstance(document, dict):
        source = document.get("source")
        if (
            isinstance(source, dict)
            and isinstance(source.get("group_id"), str)
            and isinstance(source.get("split"), str)
        ):
            yield source["group_id"], source["split"]
        if isinstance(document.get("group_id"), str) and isinstance(document.get("split"), str):
            yield document["group_id"], document["split"]
        for key in ("samples", "records", "images"):
            if isinstance(document.get(key), list):
                for item in document[key]:
                    yield from _group_split_pairs(item)
    elif isinstance(document, list):
        for item in document:
            yield from _group_split_pairs(item)


def validate_split_groups(documents: Iterable[tuple[str, Any]]) -> list[str]:
    """Detect a capture/source group assigned to more than one data split."""
    assignments: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for origin, document in documents:
        for group_id, split in _group_split_pairs(document):
            if split != "unassigned":
                assignments[group_id][split].add(origin)
    errors: list[str] = []
    for group_id, by_split in sorted(assignments.items()):
        if len(by_split) > 1:
            detail = ", ".join(
                f"{split} ({', '.join(sorted(origins))})"
                for split, origins in sorted(by_split.items())
            )
            errors.append(f"split overlap: group {group_id!r} appears in {detail}")
    return errors


def validate_packages(
    package_paths: Sequence[Path | str],
    *,
    ontology_path: Path | str,
    manifest_paths: Sequence[Path | str] = (),
    check_split_overlap: bool = False,
) -> list[str]:
    ontology = load_ontology(ontology_path)
    errors: list[str] = []
    split_documents: list[tuple[str, Any]] = []
    seen_record_ids: dict[str, str] = {}
    seen_image_ids: dict[str, str] = {}
    seen_source_hashes: dict[str, tuple[str, str | None]] = {}
    seen_annotation_ids: dict[str, str] = {}
    for package_path in package_paths:
        path = Path(package_path)
        for line_number, record in read_jsonl(path):
            location = f"{path}:{line_number}"
            errors.extend(validate_record(record, ontology, location=location))
            split_documents.append((location, record))
            if isinstance(record, dict):
                record_id = record.get("record_id")
                if isinstance(record_id, str):
                    if record_id in seen_record_ids:
                        errors.append(
                            f"{location}.record_id: duplicate {record_id!r}; first seen at {seen_record_ids[record_id]}"
                        )
                    else:
                        seen_record_ids[record_id] = location
                image_id = record.get("image_id")
                if isinstance(image_id, str):
                    if image_id in seen_image_ids:
                        errors.append(
                            f"{location}.image_id: duplicate {image_id!r}; "
                            f"first seen at {seen_image_ids[image_id]}"
                        )
                    else:
                        seen_image_ids[image_id] = location
                source = record.get("source")
                if isinstance(source, dict):
                    digest = source.get("source_image_sha256")
                    group_id = (
                        source.get("group_id") if isinstance(source.get("group_id"), str) else None
                    )
                    if isinstance(digest, str) and SHA256_RE.fullmatch(digest):
                        digest_key = digest.lower()
                        if digest_key in seen_source_hashes:
                            first_origin, first_group_id = seen_source_hashes[digest_key]
                            errors.append(
                                f"{location}.source.source_image_sha256: duplicate exact image hash "
                                f"{digest_key!r}; first seen at {first_origin}"
                            )
                            if group_id != first_group_id:
                                errors.append(
                                    f"{location}.source.group_id: exact image hash {digest_key!r} has "
                                    f"inconsistent group IDs {first_group_id!r} and {group_id!r}"
                                )
                        else:
                            seen_source_hashes[digest_key] = (location, group_id)
                for annotation in record.get("annotations", []):
                    if isinstance(annotation, dict) and isinstance(
                        annotation.get("annotation_id"), str
                    ):
                        annotation_id = annotation["annotation_id"]
                        if annotation_id in seen_annotation_ids:
                            errors.append(
                                f"{location}: duplicate package annotation ID {annotation_id!r}; first seen at {seen_annotation_ids[annotation_id]}"
                            )
                        else:
                            seen_annotation_ids[annotation_id] = location
    if check_split_overlap:
        for manifest_path in manifest_paths:
            path = Path(manifest_path)
            try:
                document = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AnnotationValidationError(f"Could not read manifest {path}: {exc}") from exc
            split_documents.append((str(path), document))
        errors.extend(validate_split_groups(split_documents))
    return errors


def _default_ontology() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "ontology.v1.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path, help="JSONL package(s) to validate")
    parser.add_argument("--ontology", type=Path, default=_default_ontology())
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        type=Path,
        help="JSON manifest included in split-overlap checks",
    )
    parser.add_argument("--check-split-overlap", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        errors = validate_packages(
            args.packages,
            ontology_path=args.ontology,
            manifest_paths=args.manifest,
            check_split_overlap=args.check_split_overlap,
        )
    except AnnotationValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1
    print(f"Validated {len(args.packages)} annotation package(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
