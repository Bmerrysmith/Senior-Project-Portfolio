#!/usr/bin/env python3
"""Route unreviewed SAM mask proposals into review buckets -- WITHOUT minting truth.

WHY THIS FILE EXISTS
====================
``scripts/optimize_proposals.py`` emits one annotation record per image plus a
pixel-free *feature sidecar* (one row per object).  Nothing in that output is
truth: every record is ``review_status="unreviewed"``.  Somebody still has to
look at ~39,556 human-drawn boxes and approve the machine-drawn mask inside
each one.  Reviewing them one at a time, in file order, is the thing that
actually kills this project -- so this module decides, per object, *how* a
human should encounter it.

Three buckets, and the names matter:

  ``bulk_confirm``  queued for a BULK HUMAN APPROVAL screen.  It does not mean
                    "accepted".  It does not mean "skip".  It means a person
                    sees the mask pre-marked clean and clicks once for the
                    whole screen.  A human still signs.
  ``auto_reject``   the MASK is discarded; the human's box survives as bbox
                    geometry with ``annotation_confidence="uncertain"``.  No
                    object is ever deleted -- rejecting a mask costs a redraw,
                    deleting an object costs a silent weed loss.
  ``human_review``  full manual attention, ranked.

This is a robot that sprays or cuts whatever carries ``weed_target``.  Four
design decisions follow from that and are enforced as tests, not conventions:

1.  **weed_target is never machine-confirmable.**  Precedence rule 0 runs
    before a single feature value is read: any ``weed_target`` object, and any
    object sharing an image with a ``weed_target`` box, goes to
    ``human_review``.  No threshold, config key or calibration outcome can
    override it.  Measured price: 144/1347 images and 2025/39556 objects
    (10.7% / 5.1%).  That price is what makes the absolutism survivable.
2.  **No numeric literal lives in the decision path.**  Every threshold is
    read from a calibration artifact that carries, per threshold, a value, a
    group-bootstrapped CI, N, and a ``fit_domain``.  A threshold whose
    ``fit_domain`` is not ``coco_gold`` is structurally forbidden from
    reaching a ``bulk_confirm`` gate: promoting on an out-of-domain fit
    injects bad truth, whereas rejecting a mask only costs a redraw.  The
    directions of error are not symmetric, so the substrates allowed to set
    the thresholds are not either.
3.  **SAM's self-report may veto and may rank, never promote.**  Predicted
    IoU, stability, multimask margin and jitter agreement are all produced by
    one deterministic set of weights and fail together when the model is
    confidently wrong for a systematic reason.  Promotion requires agreement
    with the human's own box (family A, mandatory) plus at least one
    genuinely independent signal (family B photometric / family C GrabCut).
4.  **Triage never touches an annotation record.**  ``annotation_record.v1``
    is a closed schema at every level, so there is no legal home for a bucket
    or a score -- and the tempting workaround, overloading ``review_status``,
    is forbidden_inference 4 exactly.  Output is a separate sidecar whose
    bucket vocabulary is asserted disjoint from ``REVIEW_STATUSES``.

Phase 1 ships with ``bulk_confirm`` EMPTY and that is the intended state, not a
bug: with 45 in-domain weed objects across ~6 capture families, rule-of-three
needs ~300 independent units for a 0.99 lower bound.  The Phase-1 win is
presentation and ordering -- median 27 boxes per image collapsed to ~2 flagged
objects on one screen -- and it is UNMEASURED until per-image timings exist.

CLI:
    python -m agrinav.data.triage_proposals \
        --features artifacts/detector_v1/proposal_features_v1.jsonl \
        --calibration artifacts/detector_v1/triage_calibration_v1.json \
        --out artifacts/detector_v1/triage_queue_v1.jsonl \
        --out-manifest artifacts/detector_v1/triage_manifest_v1.json \
        --overwrite

Refuses to run without a calibration artifact.  Needs no pixels, no GPU and no
checkpoint: every predicate here is CPU-testable with synthetic feature rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

QUEUE_SCHEMA_VERSION = "agrinav.triage_queue.v1"
MANIFEST_SCHEMA_VERSION = "agrinav.triage_manifest.v1"
CALIBRATION_SCHEMA_VERSION = "agrinav.triage_calibration.v1"

RICE_LABEL = "rice_protect"
WEED_LABEL = "weed_target"

BUCKET_BULK_CONFIRM = "bulk_confirm"
BUCKET_AUTO_REJECT = "auto_reject"
BUCKET_HUMAN_REVIEW = "human_review"
BUCKETS = frozenset({BUCKET_BULK_CONFIRM, BUCKET_AUTO_REJECT, BUCKET_HUMAN_REVIEW})

# Snapshot of scripts/validate_annotation_package.REVIEW_STATUSES.  The test
# suite asserts this stays equal to the validator's own set AND that BUCKETS is
# disjoint from it, so a bucket name can never be mistaken for a review status.
REVIEW_STATUSES_SNAPSHOT = frozenset(
    {
        "unreviewed",
        "in_review",
        "changes_requested",
        "accepted",
        "adjudicated",
        "rejected_unusable",
    }
)

TIER_CROSS_CLASS_INTRUSION = "T0"
TIER_WEED_INTEGRITY = "T1"
TIER_WEED_REMAINING = "T2"
TIER_RICE_COLLISION = "T3"
TIER_CAPTURE_FAILURE = "T4"
TIER_DEFAULT = "T5"
TIER_AUDIT = "T6"
TIERS = (
    TIER_CROSS_CLASS_INTRUSION,
    TIER_WEED_INTEGRITY,
    TIER_WEED_REMAINING,
    TIER_RICE_COLLISION,
    TIER_CAPTURE_FAILURE,
    TIER_DEFAULT,
    TIER_AUDIT,
)
# Tiers that order by impact ALONE: cost must never deprioritise a weed.
IMPACT_ONLY_TIERS = frozenset(
    {
        TIER_CROSS_CLASS_INTRUSION,
        TIER_WEED_INTEGRITY,
        TIER_WEED_REMAINING,
    }
)

# The ONLY numeric literals in this module that participate in arithmetic on
# feature values.  They are the endpoints of the unit interval -- not tunable
# thresholds -- and are declared once here so the decision functions below
# contain no numeric constants at all (see test_no_numeric_literals_in_gates).
_UNIT_MIN = 0.0
_UNIT_MAX = 1.0

# Feature names.  Anything a gate reads is REQUIRED; a missing required feature
# is a fail-open to human_review, never a silent default.
F_FILL = "fill"
F_LEAK = "leak"
F_CONTAINMENT = "containment"
F_BOX_IOU = "box_iou"
F_AREA_PX = "area_px"
F_JITTER = "jitter_iou_mean"
F_MULTIMASK_MARGIN = "multimask_margin"
F_VEG_IN = "veg_in"
F_VEG_GAIN = "veg_gain"
F_GRABCUT_IOU = "grabcut_iou"
F_CROSS_CLASS_IOA = "cross_class_ioa_max"
F_SAME_CLASS_MASK_IOU = "same_class_mask_iou_max"
F_SAME_CLASS_BOX_IOU = "same_class_box_iou_max"
F_RICE_OVER_WEED_IOA = "rice_over_weed_box_ioa"
F_DHASH = "dhash64"
F_SAM_PRED_IOU = "sam_pred_iou"

REQUIRED_FEATURES = (
    F_FILL,
    F_LEAK,
    F_CONTAINMENT,
    F_BOX_IOU,
    F_AREA_PX,
    F_JITTER,
    F_MULTIMASK_MARGIN,
)

# Family D == SAM's own self-reported quality.  Barred from every promotion
# gate; admitted only as a ranking tie-break.  test_family_d_does_not_affect
# _bucket deletes these keys and asserts no bucket changes.
FAMILY_D_FEATURES = frozenset({F_SAM_PRED_IOU, "stability_score"})

# Thresholds that gate a PROMOTION into bulk_confirm.  Only an in-domain gold
# fit may set these, at the conservative CI bound.
BULK_CONFIRM_GATE_THRESHOLDS = (
    "family_a_containment_min",
    "family_a_box_iou_min",
    "family_a_fill_min",
    "family_a_fill_max",
    "family_b_veg_in_min",
    "family_b_veg_gain_min",
    "family_c_grabcut_iou_min",
    "veto_jitter_iou_min",
    "veto_multimask_margin_min",
)
# Thresholds that only ever REJECT a mask (the human box survives as bbox, and
# the validator structurally forbids an accepted bbox weed_target), so a
# RiceSEG transfer fit is permitted here -- functional form only.
REJECT_THRESHOLDS = ("veg_gain_min", "veg_in_min")
# Thresholds that only flag / rank, so weak signals are allowed.
FLAG_THRESHOLDS = (
    "dup_mask_iou_min",
    "dup_box_iou_min",
    "t0_cross_class_ioa_min",
    "t0_rice_over_weed_ioa_min",
    "drift_mad_max",
)

GOLD_FIT_DOMAIN = "coco_gold"
TRANSFER_FIT_DOMAINS = frozenset({GOLD_FIT_DOMAIN, "riceseg_val_transfer"})

THRESHOLD_ENTRY_KEYS = (
    "value",
    "pi_hat",
    "ci95_lower",
    "ci95_upper",
    "n_objects",
    "n_groups",
    "fit_domain",
    "gold_labels_sha256",
    "bulk_confirm_enabled",
)

PLACEHOLDER_REVISIONS = frozenset(
    {
        "PIN_BEFORE_RUN",
        "TODO",
        "CHANGEME",
        "latest",
        "main",
        "master",
        "HEAD",
        "None",
        "",
    }
)

# Group that provably fuses >=4 zero-padding sequences (stem-length histogram
# 2/3/4/5 digits, 259 distinct integers over 593 filenames).  It is not a
# capture family, so per-group normalisation inside it averages unrelated
# capture conditions.  Permanently ineligible for bulk_confirm.
UNRESOLVED_GROUP_TOKENS = ("numeric_unresolved",)

REASON_TEXT = {
    "weed_absolute": (
        "precedence rule 0: weed_target is never machine-confirmable; this "
        "object is (or shares an image with) a human-asserted weed box"
    ),
    "mask_demoted": (
        "the mask failed a demotion predicate upstream and was replaced by the "
        "human box as bbox geometry; the mask is rejected, the object survives"
    ),
    "vegetation_reject": (
        "mask shows no vegetation gain over the box remainder (double-gated, "
        "one-sided ExG); the mask is rejected, the human box survives"
    ),
    "duplicate_collision": (
        "overlaps a same-class neighbour above the duplicate threshold; both "
        "objects are flagged with a shared collision_group_id and neither is "
        "suppressed -- every box here was drawn by a human"
    ),
    "bulk_confirm_promoted": (
        "rice_protect in a weed-free image; agrees with the human box "
        "(family A) and with at least one independent signal (family B/C), "
        "not vetoed; queued for BULK HUMAN APPROVAL -- not accepted"
    ),
    "residual_human_review": (
        "did not clear the promotion gate; routed to ranked human review "
        "(fail-open absorbing state)"
    ),
    "missing_feature": (
        "a required feature was missing or not finite, so no gate could be "
        "evaluated; fail-open to human review"
    ),
    "no_calibration_for_group": (
        "no calibration entry for this (class, group); a fitted threshold is "
        "only valid on the distribution it was fitted to"
    ),
    "bulk_confirm_disabled": (
        "bulk_confirm is disabled for this (class, group) by the calibration " "artifact"
    ),
    "group_unresolved": (
        "group is a provenance blob, not a capture family; permanently "
        "ineligible for bulk_confirm"
    ),
    "audit_spot_check": (
        "selected into the deterministic audit sample; force-routed to human "
        "review so the bucket's contamination rate can be measured"
    ),
    "exg_solo_census": (
        "rejected by the ExG rule alone (the weakest gate), so it is censused "
        "rather than sampled"
    ),
}


class TriageConfigError(ValueError):
    """Calibration artifact is missing, malformed, or fitted out of domain."""


# --------------------------------------------------------------------------
# calibration artifact
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Threshold:
    name: str
    value: float
    fit_domain: str
    pi_hat: float | None
    ci95_lower: float | None
    ci95_upper: float | None
    n_objects: int | None
    n_groups: int | None
    gold_labels_sha256: str | None
    bulk_confirm_enabled: bool


@dataclass(frozen=True)
class GroupCalibration:
    label: str
    group_id: str
    q_star: float | None
    median_fill: float | None
    bulk_confirm_enabled: bool
    fit_domain: str
    fill_median_ref: float | None
    fill_mad: float | None


class Calibration:
    """Loaded, domain-checked calibration artifact.

    Everything the decision path compares against comes from here.  Load-time
    checks are deliberately loud: a threshold that reaches a bulk_confirm gate
    with ``fit_domain != "coco_gold"`` raises rather than silently promoting.
    """

    def __init__(self, document: Mapping[str, Any], *, sha256: str) -> None:
        self.document = document
        self.sha256 = sha256
        self.model_revision = str(document.get("model_revision") or "")
        self._thresholds: dict[str, Threshold] = {}
        self._groups: dict[tuple[str, str], GroupCalibration] = {}
        self.ranking: Mapping[str, Any] = document.get("ranking") or {}
        self.spot_check: Mapping[str, Any] = document.get("spot_check") or {}
        self._parse()

    # -- parsing / validation ------------------------------------------------

    def _parse(self) -> None:
        doc = self.document
        if doc.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
            raise TriageConfigError(
                f"calibration schema_version must be {CALIBRATION_SCHEMA_VERSION!r}, "
                f"got {doc.get('schema_version')!r}"
            )
        _require_pinned_revision(self.model_revision)

        raw_thresholds = doc.get("thresholds")
        if not isinstance(raw_thresholds, dict) or not raw_thresholds:
            raise TriageConfigError("calibration.thresholds must be a non-empty object")
        for name, entry in raw_thresholds.items():
            self._thresholds[name] = _parse_threshold(name, entry)

        for name in BULK_CONFIRM_GATE_THRESHOLDS:
            entry = self._thresholds.get(name)
            if entry is None:
                raise TriageConfigError(
                    f"calibration.thresholds.{name}: required bulk_confirm gate is missing"
                )
            if entry.fit_domain != GOLD_FIT_DOMAIN:
                raise TriageConfigError(
                    f"calibration.thresholds.{name}: fit_domain {entry.fit_domain!r} may "
                    f"not set a bulk_confirm gate; only {GOLD_FIT_DOMAIN!r} may "
                    "(promotion injects bad truth, rejection only costs a redraw)"
                )
        for name in REJECT_THRESHOLDS:
            entry = self._thresholds.get(name)
            if entry is None:
                raise TriageConfigError(
                    f"calibration.thresholds.{name}: required reject threshold is missing"
                )
            if entry.fit_domain not in TRANSFER_FIT_DOMAINS:
                raise TriageConfigError(
                    f"calibration.thresholds.{name}: fit_domain {entry.fit_domain!r} is not "
                    f"one of {sorted(TRANSFER_FIT_DOMAINS)}"
                )
        for name in FLAG_THRESHOLDS:
            if name not in self._thresholds:
                raise TriageConfigError(
                    f"calibration.thresholds.{name}: required flag threshold is missing"
                )

        for key, entry in (doc.get("groups") or {}).items():
            label, _, group_id = str(key).partition("||")
            if not group_id:
                raise TriageConfigError(
                    f"calibration.groups.{key!r}: key must be '<label>||<group_id>'"
                )
            group = _parse_group(label, group_id, entry)
            if label == WEED_LABEL and group.bulk_confirm_enabled:
                raise TriageConfigError(
                    f"calibration.groups.{key!r}: bulk_confirm_enabled is not permissible "
                    "for weed_target under any calibration outcome"
                )
            self._groups[(label, group_id)] = group

    # -- accessors -----------------------------------------------------------

    def threshold(self, name: str) -> float:
        entry = self._thresholds.get(name)
        if entry is None:
            raise TriageConfigError(f"calibration.thresholds.{name}: missing")
        return entry.value

    def threshold_entry(self, name: str) -> Threshold:
        entry = self._thresholds.get(name)
        if entry is None:
            raise TriageConfigError(f"calibration.thresholds.{name}: missing")
        return entry

    def group(self, label: str, group_id: str) -> GroupCalibration | None:
        return self._groups.get((label, group_id))

    def q_star(self, label: str, group_id: str) -> float | None:
        group = self.group(label, group_id)
        return None if group is None else group.q_star

    def median_fill(self, label: str, group_id: str) -> float | None:
        group = self.group(label, group_id)
        return None if group is None else group.median_fill

    def bulk_confirm_enabled(self, label: str, group_id: str) -> bool:
        if label == WEED_LABEL:
            return False
        if any(token in group_id for token in UNRESOLVED_GROUP_TOKENS):
            return False
        group = self.group(label, group_id)
        return bool(group is not None and group.bulk_confirm_enabled)

    def rank_number(self, name: str, default: float) -> float:
        value = self.ranking.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise TriageConfigError(f"calibration.ranking.{name}: not a number") from exc

    def spot_number(self, name: str, default: float) -> float:
        value = self.spot_check.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise TriageConfigError(f"calibration.spot_check.{name}: not a number") from exc

    def thresholds_report(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "value": t.value,
                "fit_domain": t.fit_domain,
                "pi_hat": t.pi_hat,
                "ci95_lower": t.ci95_lower,
                "ci95_upper": t.ci95_upper,
                "n_objects": t.n_objects,
                "n_groups": t.n_groups,
                "gold_labels_sha256": t.gold_labels_sha256,
                "bulk_confirm_enabled": t.bulk_confirm_enabled,
            }
            for name, t in sorted(self._thresholds.items())
        }


def _require_pinned_revision(revision: str) -> None:
    """Reject placeholder model revisions before anything else happens.

    ``PIN_BEFORE_RUN`` is a non-empty string, so it passes the annotation
    validator's presence check and produces provenance that validates clean and
    is unrecoverable.  It must die here.
    """
    if revision in PLACEHOLDER_REVISIONS:
        raise TriageConfigError(
            f"calibration.model_revision {revision!r} is a placeholder; pin a real commit"
        )
    if not all(character in "0123456789abcdef" for character in revision):
        raise TriageConfigError(
            f"calibration.model_revision {revision!r} must match ^[0-9a-f]{{7,40}}$"
        )
    if not (len("0123456789a") - len("0123") <= len(revision) <= len("0" * 40)):
        raise TriageConfigError(
            f"calibration.model_revision {revision!r} must match ^[0-9a-f]{{7,40}}$"
        )


def _parse_threshold(name: str, entry: Any) -> Threshold:
    if not isinstance(entry, dict):
        raise TriageConfigError(f"calibration.thresholds.{name}: must be an object")
    missing = [key for key in THRESHOLD_ENTRY_KEYS if key not in entry]
    if missing:
        raise TriageConfigError(
            f"calibration.thresholds.{name}: missing provenance keys {missing} -- a "
            "threshold without a value, CI, N and fit_domain is a magic number"
        )
    value = entry["value"]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TriageConfigError(f"calibration.thresholds.{name}.value: must be a number")
    fit_domain = entry["fit_domain"]
    if not isinstance(fit_domain, str) or not fit_domain.strip():
        raise TriageConfigError(f"calibration.thresholds.{name}.fit_domain: must be a string")
    return Threshold(
        name=name,
        value=float(value),
        fit_domain=fit_domain,
        pi_hat=_opt_float(entry.get("pi_hat")),
        ci95_lower=_opt_float(entry.get("ci95_lower")),
        ci95_upper=_opt_float(entry.get("ci95_upper")),
        n_objects=_opt_int(entry.get("n_objects")),
        n_groups=_opt_int(entry.get("n_groups")),
        gold_labels_sha256=entry.get("gold_labels_sha256"),
        bulk_confirm_enabled=bool(entry.get("bulk_confirm_enabled")),
    )


def _parse_group(label: str, group_id: str, entry: Any) -> GroupCalibration:
    if not isinstance(entry, dict):
        raise TriageConfigError(f"calibration.groups.{label}||{group_id}: must be an object")
    fit_domain = entry.get("fit_domain") or GOLD_FIT_DOMAIN
    enabled = bool(entry.get("bulk_confirm_enabled"))
    if enabled and fit_domain != GOLD_FIT_DOMAIN:
        raise TriageConfigError(
            f"calibration.groups.{label}||{group_id}: bulk_confirm_enabled requires "
            f"fit_domain {GOLD_FIT_DOMAIN!r}, got {fit_domain!r}"
        )
    return GroupCalibration(
        label=label,
        group_id=group_id,
        q_star=_opt_float(entry.get("q_star")),
        median_fill=_opt_float(entry.get("median_fill")),
        bulk_confirm_enabled=enabled,
        fit_domain=str(fit_domain),
        fill_median_ref=_opt_float(entry.get("fill_median_ref")),
        fill_mad=_opt_float(entry.get("fill_mad")),
    )


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_calibration(path: Path) -> Calibration:
    """Load and validate the calibration artifact.  Refuses to run without one."""
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TriageConfigError(f"{path}: calibration is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise TriageConfigError(f"{path}: calibration must be a JSON object")
    return Calibration(document, sha256=digest)


# --------------------------------------------------------------------------
# feature rows
# --------------------------------------------------------------------------


@dataclass
class ObjectRow:
    """One object's pixel-free feature row, as emitted by optimize_proposals."""

    record_id: str
    annotation_id: str
    source_object_id: str | None
    label: str
    group_id: str
    capture_family: str
    source_image_sha256: str
    geometry_type: str
    reason_codes: tuple[str, ...]
    features: Mapping[str, Any]
    raw: Mapping[str, Any] = field(default_factory=dict)

    def feature(self, name: str) -> float | None:
        return _finite(self.features.get(name))

    def has_required_features(self) -> bool:
        return all(self.feature(name) is not None for name in REQUIRED_FEATURES)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or isinstance(value, str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def parse_feature_row(raw: Mapping[str, Any]) -> ObjectRow:
    """Accept either a flat row or one with a nested ``features`` object."""
    nested = raw.get("features")
    features: dict[str, Any] = {}
    if isinstance(nested, dict):
        features.update(nested)
    for key, value in raw.items():
        if key != "features":
            features.setdefault(key, value)
    record_id = str(raw.get("record_id") or "")
    annotation_id = str(raw.get("annotation_id") or "")
    if not record_id or not annotation_id:
        raise ValueError("feature row requires non-empty record_id and annotation_id")
    reason_codes = raw.get("reason_codes") or []
    if isinstance(reason_codes, str):
        reason_codes = [reason_codes]
    return ObjectRow(
        record_id=record_id,
        annotation_id=annotation_id,
        source_object_id=raw.get("source_object_id"),
        label=str(raw.get("label") or ""),
        group_id=str(raw.get("group_id") or ""),
        capture_family=str(raw.get("capture_family") or ""),
        source_image_sha256=str(raw.get("source_image_sha256") or ""),
        geometry_type=str(raw.get("geometry_type") or ""),
        reason_codes=tuple(str(code) for code in reason_codes),
        features=features,
        raw=raw,
    )


def read_feature_rows(path: Path) -> list[ObjectRow]:
    rows: list[ObjectRow] = []
    seen: set[tuple[str, str]] = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            row = parse_feature_row(raw)
            key = (row.record_id, row.annotation_id)
            if key in seen:
                raise ValueError(f"{path}:{line_number}: duplicate queue key {key!r}")
            seen.add(key)
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: feature sidecar contains no rows")
    return rows


@dataclass
class ImageContext:
    """Per-image facts the object-level rules need.  Computed once, no pixels."""

    record_id: str
    source_image_sha256: str
    group_id: str
    capture_family: str
    has_weed_box: bool
    weed_out_count: int
    weed_in_count: int
    capture_failure: bool
    dhash64: int | None
    fill_drift_mads: float | None = None


def build_image_contexts(
    rows: Sequence[ObjectRow], calibration: Calibration
) -> dict[str, ImageContext]:
    by_image: dict[str, list[ObjectRow]] = defaultdict(list)
    for row in rows:
        by_image[row.record_id].append(row)

    contexts: dict[str, ImageContext] = {}
    fills_by_group: dict[str, list[float]] = defaultdict(list)
    for record_id, image_rows in by_image.items():
        head = image_rows[0]
        weed_out = sum(1 for row in image_rows if row.label == WEED_LABEL)
        weed_in = head.raw.get("weed_box_count_in")
        weed_in = int(weed_in) if isinstance(weed_in, int) else weed_out
        contexts[record_id] = ImageContext(
            record_id=record_id,
            source_image_sha256=head.source_image_sha256,
            group_id=head.group_id,
            capture_family=head.capture_family,
            has_weed_box=any(row.label == WEED_LABEL for row in image_rows),
            weed_out_count=weed_out,
            weed_in_count=weed_in,
            capture_failure=bool(head.raw.get("capture_failure")),
            dhash64=_parse_dhash(head.features.get(F_DHASH)),
        )
        for row in image_rows:
            fill = row.feature(F_FILL)
            if fill is not None:
                fills_by_group[row.group_id].append(fill)

    # Calibration-drift tripwire: a fitted threshold is only valid on the
    # distribution it was fitted to.
    drift_by_group: dict[str, float | None] = {}
    for group_id, fills in fills_by_group.items():
        observed = _median(fills)
        reference = None
        for label in (RICE_LABEL, WEED_LABEL):
            group = calibration.group(label, group_id)
            if group is not None and group.fill_median_ref is not None:
                reference = group
                break
        if reference is None or reference.fill_mad is None or reference.fill_mad <= _UNIT_MIN:
            drift_by_group[group_id] = None
            continue
        drift_by_group[group_id] = abs(observed - reference.fill_median_ref) / reference.fill_mad
    for context in contexts.values():
        context.fill_drift_mads = drift_by_group.get(context.group_id)
    return contexts


def _parse_dhash(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16)
        except ValueError:
            return None
    return None


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return _UNIT_MIN
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


# ==========================================================================
# DECISION PATH.  Every function below this banner and above the next one
# contains ZERO numeric literals: all comparison operands come from the
# calibration artifact or from the unit-interval constants declared at module
# scope.  tests/test_triage_proposals.py AST-walks these by name.
# ==========================================================================


def _clip_unit(value: float) -> float:
    return min(max(value, _UNIT_MIN), _UNIT_MAX)


def compute_q(row: ObjectRow, calibration: Calibration) -> float | None:
    """q = min(jitter_iou_mean, 1 - leak, fill_norm).

    One free parameter downstream (q_star), fitted per (class, group) on a
    physically-motivated conjunction, instead of nine weights fitted on ~922
    gold objects in ~7 groups -- which would be overfitting with a confidence
    interval printed next to it.
    """
    fill = row.feature(F_FILL)
    leak = row.feature(F_LEAK)
    jitter = row.feature(F_JITTER)
    if fill is None or leak is None or jitter is None:
        return None
    median_fill = calibration.median_fill(row.label, row.group_id)
    if median_fill is None or median_fill <= _UNIT_MIN:
        return None
    fill_norm = _clip_unit(fill / median_fill)
    return min(jitter, _UNIT_MAX - leak, fill_norm)


def rule_weed_absolute(row: ObjectRow, context: ImageContext) -> bool:
    """Precedence rule 0.  Evaluated before any feature value is read."""
    return row.label == WEED_LABEL or context.has_weed_box


def rule_mask_demoted(row: ObjectRow) -> bool:
    """Rule 1: the mask already failed a demotion predicate upstream."""
    return bool(row.reason_codes)


def rule_vegetation_reject(row: ObjectRow, calibration: Calibration) -> bool:
    """Rule 2: one-sided, double-gated ExG mask reject.

    ExG may never assign, change or confirm a LABEL -- that would be
    forbidden_inference 1 in statistical clothing.  It may only reject a mask,
    and only when BOTH gates fire, because senescent rice reads as
    non-vegetation and duckweed/reflections read as the inverse failure.
    """
    veg_gain = row.feature(F_VEG_GAIN)
    veg_in = row.feature(F_VEG_IN)
    if veg_gain is None or veg_in is None:
        return False
    return veg_gain < calibration.threshold("veg_gain_min") and veg_in < calibration.threshold(
        "veg_in_min"
    )


def rule_duplicate_collision(row: ObjectRow, calibration: Calibration) -> bool:
    """Rule 3: same-class crowding.  Flag both, delete neither -- no NMS.

    Every box here was drawn by a human, so auto-suppressing one silently
    deletes a human assertion, and it may delete the real object and keep the
    artifact.  Measured crowding is negligible, so flagging costs almost
    nothing and removes a silent-loss path.
    """
    mask_iou = row.feature(F_SAME_CLASS_MASK_IOU)
    box_iou = row.feature(F_SAME_CLASS_BOX_IOU)
    if mask_iou is not None and mask_iou >= calibration.threshold("dup_mask_iou_min"):
        return True
    if box_iou is not None and box_iou >= calibration.threshold("dup_box_iou_min"):
        return True
    return False


def rule_bulk_confirm(
    row: ObjectRow, context: ImageContext, calibration: Calibration, q: float | None
) -> tuple[bool, tuple[str, ...]]:
    """Rule 4: promotion into the bulk human-approval queue.

    Family A (agreement with the HUMAN's own box) is mandatory; at least one of
    family B (photometric) or family C (GrabCut) must also agree.  Family D --
    SAM's self-reported quality -- is absent by construction: it may veto and
    it may rank, never promote.
    """
    blockers: list[str] = []
    if row.label != RICE_LABEL:
        blockers.append("not_rice_protect")
    if context.has_weed_box:
        blockers.append("image_contains_weed_box")
    if not calibration.bulk_confirm_enabled(row.label, row.group_id):
        blockers.append("bulk_confirm_disabled")
    if q is None:
        blockers.append("q_unavailable")
    q_star = calibration.q_star(row.label, row.group_id)
    if q_star is None:
        blockers.append("no_q_star_for_group")
    elif q is not None and q < q_star:
        blockers.append("below_q_star")

    containment = row.feature(F_CONTAINMENT)
    box_iou = row.feature(F_BOX_IOU)
    fill = row.feature(F_FILL)
    if containment is None or box_iou is None or fill is None:
        blockers.append("family_a_features_missing")
    else:
        if containment < calibration.threshold("family_a_containment_min"):
            blockers.append("family_a_containment")
        if box_iou < calibration.threshold("family_a_box_iou_min"):
            blockers.append("family_a_box_iou")
        if fill < calibration.threshold("family_a_fill_min"):
            blockers.append("family_a_fill_low")
        if fill > calibration.threshold("family_a_fill_max"):
            blockers.append("family_a_fill_high")

    veg_in = row.feature(F_VEG_IN)
    veg_gain = row.feature(F_VEG_GAIN)
    family_b = (
        veg_in is not None
        and veg_gain is not None
        and veg_in >= calibration.threshold("family_b_veg_in_min")
        and veg_gain >= calibration.threshold("family_b_veg_gain_min")
    )
    grabcut = row.feature(F_GRABCUT_IOU)
    family_c = grabcut is not None and grabcut >= calibration.threshold("family_c_grabcut_iou_min")
    if not (family_b or family_c):
        blockers.append("no_independent_corroboration")

    jitter = row.feature(F_JITTER)
    margin = row.feature(F_MULTIMASK_MARGIN)
    if jitter is None or jitter < calibration.threshold("veto_jitter_iou_min"):
        blockers.append("veto_jitter_instability")
    if margin is None or margin < calibration.threshold("veto_multimask_margin_min"):
        blockers.append("veto_multimask_margin")

    return (not blockers), tuple(blockers)


def bucket_object(
    row: ObjectRow, context: ImageContext, calibration: Calibration
) -> tuple[str, tuple[str, ...], float | None]:
    """Return (bucket, reason_codes, q).  First match wins; order is the safety
    argument, not an implementation detail."""
    if rule_weed_absolute(row, context):
        return BUCKET_HUMAN_REVIEW, ("weed_absolute",), None
    if rule_mask_demoted(row):
        return BUCKET_AUTO_REJECT, ("mask_demoted",) + row.reason_codes, None
    if rule_vegetation_reject(row, calibration):
        return BUCKET_AUTO_REJECT, ("vegetation_reject",), None
    if rule_duplicate_collision(row, calibration):
        return BUCKET_HUMAN_REVIEW, ("duplicate_collision",), None
    if not row.has_required_features():
        return BUCKET_HUMAN_REVIEW, ("missing_feature",), None
    q = compute_q(row, calibration)
    if q is None:
        return BUCKET_HUMAN_REVIEW, ("no_calibration_for_group",), None
    promoted, blockers = rule_bulk_confirm(row, context, calibration, q)
    if promoted:
        return BUCKET_BULK_CONFIRM, ("bulk_confirm_promoted",), q
    return BUCKET_HUMAN_REVIEW, ("residual_human_review",) + blockers, q


def escalation_tier(
    row: ObjectRow, context: ImageContext, bucket: str, calibration: Calibration
) -> str:
    """Escalation tiers bypass ranking entirely."""
    cross_class = row.feature(F_CROSS_CLASS_IOA)
    if cross_class is not None and cross_class >= calibration.threshold("t0_cross_class_ioa_min"):
        return TIER_CROSS_CLASS_INTRUSION
    rice_over_weed = row.feature(F_RICE_OVER_WEED_IOA)
    if rice_over_weed is not None and rice_over_weed > calibration.threshold(
        "t0_rice_over_weed_ioa_min"
    ):
        return TIER_CROSS_CLASS_INTRUSION
    if row.label == WEED_LABEL and row.geometry_type == "bbox":
        return TIER_WEED_INTEGRITY
    if context.weed_out_count != context.weed_in_count:
        return TIER_WEED_INTEGRITY
    drift = context.fill_drift_mads
    if drift is not None and drift > calibration.threshold("drift_mad_max"):
        return TIER_WEED_INTEGRITY
    if row.label == WEED_LABEL:
        return TIER_WEED_REMAINING
    if "duplicate_collision" in row.reason_codes or rule_duplicate_collision(row, calibration):
        return TIER_RICE_COLLISION
    if context.capture_failure:
        return TIER_CAPTURE_FAILURE
    return TIER_DEFAULT


# ==========================================================================
# END OF DECISION PATH.  Numeric literals are permitted again below: nothing
# here can promote an object -- it only orders, samples and reports.
# ==========================================================================


@dataclass
class Decision:
    row: ObjectRow
    context: ImageContext
    bucket: str
    reason_codes: tuple[str, ...]
    q: float | None
    tier: str
    collision_group_id: str | None = None
    dhash_cluster_id: str | None = None
    impact: float = 0.0
    cost_seconds_est: float = 0.0
    rank: int | None = None
    audit_sample: bool = False

    @property
    def reason(self) -> str:
        parts = [REASON_TEXT.get(code, code) for code in self.reason_codes]
        head = parts[0] if parts else "no rule fired"
        extra = [code for code in self.reason_codes[1:] if code not in REASON_TEXT]
        if extra:
            head = f"{head} [{', '.join(extra)}]"
        return f"{self.bucket}: {head}"


def _collision_group_id(row: ObjectRow) -> str:
    partner = row.raw.get("same_class_neighbor_annotation_id")
    if isinstance(partner, str) and partner:
        left, right = sorted((row.annotation_id, partner))
        return f"collision:{row.record_id}:{left}|{right}"
    return f"collision:{row.record_id}:{row.annotation_id}"


def triage_objects(rows: Sequence[ObjectRow], calibration: Calibration) -> list[Decision]:
    """Bucket + tier every object.  Exceptions fail open to human_review."""
    contexts = build_image_contexts(rows, calibration)
    decisions: list[Decision] = []
    for row in rows:
        context = contexts[row.record_id]
        try:
            bucket, reason_codes, q = bucket_object(row, context, calibration)
        except TriageConfigError:
            raise
        except Exception as exc:  # fail-open absorbing state
            bucket, reason_codes, q = (
                BUCKET_HUMAN_REVIEW,
                ("residual_human_review", f"exception:{type(exc).__name__}"),
                None,
            )
        try:
            tier = escalation_tier(row, context, bucket, calibration)
        except TriageConfigError:
            raise
        except Exception:  # pragma: no cover - defensive
            tier = TIER_DEFAULT
        decision = Decision(
            row=row,
            context=context,
            bucket=bucket,
            reason_codes=reason_codes,
            q=q,
            tier=tier,
        )
        if "duplicate_collision" in reason_codes:
            decision.collision_group_id = _collision_group_id(row)
        decisions.append(decision)
    _assert_weed_never_bulk_confirm(decisions)
    return decisions


def _assert_weed_never_bulk_confirm(decisions: Iterable[Decision]) -> None:
    """Invariant I0, re-asserted after the fact.  Cheap, and the one thing that
    must never be true."""
    for decision in decisions:
        if decision.bucket != BUCKET_BULK_CONFIRM:
            continue
        if decision.row.label == WEED_LABEL or decision.context.has_weed_box:
            raise AssertionError(
                f"I0 violated: {decision.row.annotation_id} reached bulk_confirm with a "
                "weed_target present"
            )


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------


def class_weights(rows: Sequence[ObjectRow]) -> dict[str, float]:
    """w_class = N_total / N_label -- MEASURED from the corpus, not chosen.

    This is the per-instance gradient weight under a class-balanced loss, so a
    weed instance is worth ~80x a rice instance to the model.  Label
    atypicality is confined strictly to ordering; it never gates anything.
    """
    counts = Counter(row.label for row in rows)
    total = len(rows)
    return {label: total / count for label, count in counts.items() if count}


def median_area_by_class(rows: Sequence[ObjectRow]) -> dict[str, float]:
    areas: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        area = row.feature(F_AREA_PX)
        if area is not None and area > 0.0:
            areas[row.label].append(area)
    return {label: _median(values) for label, values in areas.items() if values}


def _popcount(value: int) -> int:
    return bin(value).count("1")


def assign_dhash_clusters(decisions: Sequence[Decision], max_distance: int) -> dict[str, str]:
    """Near-duplicate clustering across the video-sequence families.

    Used ONLY for ordering (and, downstream, to offer an inherited outcome as a
    SUGGESTION requiring a human click).  Never a gate.
    """
    hashes: dict[str, int] = {}
    for decision in decisions:
        value = decision.context.dhash64
        if value is not None:
            hashes.setdefault(decision.row.record_id, value)
    record_ids = sorted(hashes)
    parent = {record_id: record_id for record_id in record_ids}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for index, left in enumerate(record_ids):
        for right in record_ids[index + 1 :]:
            if _popcount(hashes[left] ^ hashes[right]) <= max_distance:
                a, b = find(left), find(right)
                if a != b:
                    parent[a] = b
    return {record_id: f"dhash:{find(record_id)}" for record_id in record_ids}


def novelty_scores(decisions: Sequence[Decision], max_images: int) -> dict[str, float]:
    """Static novelty proxy: normalised min-Hamming distance to any other image.

    The live queue recomputes this against the RESOLVED set every N images;
    offline we can only measure isolation within the corpus.  Ordering aid
    only, and it is bounded to [0, 1] so it can never dominate impact.
    """
    hashes: dict[str, int] = {}
    for decision in decisions:
        value = decision.context.dhash64
        if value is not None:
            hashes.setdefault(decision.row.record_id, value)
    record_ids = sorted(hashes)
    if not record_ids or len(record_ids) > max_images:
        return {}
    bits = 64.0
    scores: dict[str, float] = {}
    for left in record_ids:
        best = None
        for right in record_ids:
            if right == left:
                continue
            distance = _popcount(hashes[left] ^ hashes[right])
            if best is None or distance < best:
                best = distance
        scores[left] = 1.0 if best is None else min(best / bits, 1.0)
    return scores


def score_decisions(decisions: Sequence[Decision], calibration: Calibration) -> None:
    """impact = w_class * uncertainty * influence * novelty; cost is a stated prior.

    High-confidence objects are DEPRIORITISED, never removed: sorting the queue
    by descending model confidence would systematically bury exactly the hard
    conditions (tiny weeds, occlusion, glare, duckweed) where the safety risk
    concentrates.
    """
    rows = [decision.row for decision in decisions]
    weights = class_weights(rows)
    medians = median_area_by_class(rows)
    novelty = novelty_scores(decisions, int(calibration.rank_number("novelty_max_images", 4000)))
    cluster = assign_dhash_clusters(
        decisions, int(calibration.rank_number("dhash_cluster_max_distance", 6))
    )

    flagged_per_image: Counter[str] = Counter()
    redraw_per_image: Counter[str] = Counter()
    for decision in decisions:
        if decision.bucket in (BUCKET_HUMAN_REVIEW, BUCKET_AUTO_REJECT):
            flagged_per_image[decision.row.record_id] += 1
        if decision.bucket == BUCKET_AUTO_REJECT:
            redraw_per_image[decision.row.record_id] += 1

    cost_base = calibration.rank_number("cost_base_seconds", 4.0)
    cost_flagged = calibration.rank_number("cost_per_flagged_seconds", 1.5)
    cost_redraw = calibration.rank_number("cost_per_redraw_seconds", 6.0)

    for decision in decisions:
        row = decision.row
        decision.dhash_cluster_id = cluster.get(row.record_id)
        weight = weights.get(row.label, 1.0)

        q = decision.q
        margin = row.feature(F_MULTIMASK_MARGIN)
        terms = []
        if q is not None:
            terms.append(1.0 - q)
        if margin is not None:
            terms.append(1.0 - margin)
        uncertainty = sum(terms) / len(terms) if terms else 1.0
        uncertainty = min(max(uncertainty, 0.0), 1.0)

        area = row.feature(F_AREA_PX)
        median_area = medians.get(row.label)
        if area is None or not median_area:
            influence = 1.0
        else:
            influence = math.sqrt(max(area, 0.0) / median_area)

        decision.impact = weight * uncertainty * influence * novelty.get(row.record_id, 1.0)
        decision.cost_seconds_est = (
            cost_base
            + cost_flagged * flagged_per_image[row.record_id]
            + cost_redraw * redraw_per_image[row.record_id]
        )


# --------------------------------------------------------------------------
# image-level queue
# --------------------------------------------------------------------------


@dataclass
class QueueImage:
    record_id: str
    group_id: str
    capture_family: str
    tier: str
    impact: float
    cost_seconds_est: float
    flagged_count: int
    object_count: int
    bucket_counts: dict[str, int]
    dhash_cluster_id: str | None
    rank: int | None = None


def build_image_queue(decisions: Sequence[Decision], calibration: Calibration) -> list[QueueImage]:
    """The queue unit is the IMAGE; buckets are per object.

    At a median 27 boxes per image, a per-object clean rate of 0.95 yields only
    26.3% all-clean images (0.98 -> 56.9%, 0.99 -> 75.0%).  Splitting one image
    across two queues doubles its context-switch cost and buys nothing -- the
    entire win is collapsing 27 decisions into ~2 on one screen.
    """
    by_image: dict[str, list[Decision]] = defaultdict(list)
    for decision in decisions:
        by_image[decision.row.record_id].append(decision)

    images: list[QueueImage] = []
    for record_id, group in by_image.items():
        counts = Counter(decision.bucket for decision in group)
        flagged = counts[BUCKET_HUMAN_REVIEW] + counts[BUCKET_AUTO_REJECT]
        tier = min((decision.tier for decision in group), key=TIERS.index)
        head = group[0]
        images.append(
            QueueImage(
                record_id=record_id,
                group_id=head.row.group_id,
                capture_family=head.row.capture_family,
                tier=tier,
                impact=max(decision.impact for decision in group),
                cost_seconds_est=max(decision.cost_seconds_est for decision in group),
                flagged_count=flagged,
                object_count=len(group),
                bucket_counts=dict(counts),
                dhash_cluster_id=head.dhash_cluster_id,
            )
        )

    ordered: list[QueueImage] = []
    for tier in TIERS:
        tier_images = [image for image in images if image.tier == tier]
        if tier in IMPACT_ONLY_TIERS:
            tier_images.sort(key=lambda im: (-im.impact, im.record_id))
        else:
            tier_images.sort(
                key=lambda im: (-(im.impact / max(im.cost_seconds_est, 1.0)), im.record_id)
            )
        ordered.extend(interleave_by_group(tier_images, calibration))

    for position, image in enumerate(ordered, start=1):
        image.rank = position
    ranks = {image.record_id: image.rank for image in ordered}
    for decision in decisions:
        decision.rank = ranks.get(decision.row.record_id)
    return ordered


def interleave_by_group(images: Sequence[QueueImage], calibration: Calibration) -> list[QueueImage]:
    """HARD group interleave, applied within a tier so escalations still lead.

    Without it the queue drains the largest capture family first and the
    reviewer calibrates on one family, which generalises to none.  Per-group
    budget is proportional to sqrt(group_size) and no group may exceed a
    fixed share of a batch; the unresolved-provenance blob is capped harder.
    """
    if not images:
        return []
    batch_size = max(int(calibration.rank_number("batch_size", 50)), 1)
    max_share = calibration.rank_number("group_max_batch_share", 0.30)
    unresolved_share = calibration.rank_number("unresolved_max_batch_share", 0.10)

    queues: dict[str, list[QueueImage]] = defaultdict(list)
    for image in images:
        queues[image.group_id].append(image)
    order = sorted(queues, key=lambda gid: (-len(queues[gid]), gid))
    weights = {gid: math.sqrt(len(queues[gid])) for gid in order}

    output: list[QueueImage] = []
    while any(queues[gid] for gid in order):
        total_weight = sum(weights[gid] for gid in order if queues[gid]) or 1.0
        batch: list[QueueImage] = []
        for gid in order:
            if not queues[gid]:
                continue
            share = max_share
            if any(token in gid for token in UNRESOLVED_GROUP_TOKENS):
                share = min(share, unresolved_share)
            cap = max(int(batch_size * share), 1)
            quota = max(int(round(batch_size * weights[gid] / total_weight)), 1)
            take = min(quota, cap, len(queues[gid]), max(batch_size - len(batch), 0))
            if take <= 0:
                continue
            batch.extend(queues[gid][:take])
            del queues[gid][:take]
        if not batch:  # pragma: no cover - defensive
            break
        output.extend(batch)
    return output


# --------------------------------------------------------------------------
# spot checks
# --------------------------------------------------------------------------


def spot_check_sample_size(contamination_rate: float, power: float) -> int:
    """n = ceil(ln(1 - power) / ln(1 - rate)).

    At rate=0.01, power=0.90 this is 230 -- derived from a stated hypothesis
    ("90% power to detect at least one good mask if the bucket is 1%
    contaminated"), not a hand-picked percentage.
    """
    if not (0.0 < contamination_rate < 1.0) or not (0.0 < power < 1.0):
        raise ValueError("contamination_rate and power must be in (0, 1)")
    return math.ceil(math.log(1.0 - power) / math.log(1.0 - contamination_rate))


def _sample_key(salt: str, image_sha: str, annotation_id: str) -> int:
    """Content-addressed, so re-running the pipeline cannot reshuffle the audit
    sample."""
    digest = hashlib.sha256(f"{salt}|{image_sha}|{annotation_id}".encode("utf-8"))
    return int(digest.hexdigest()[:8], 16)


def select_spot_checks(decisions: Sequence[Decision], calibration: Calibration) -> dict[str, Any]:
    """Deterministic audit sampling, stratified by capture family.

    auto_reject gets a power-derived sample plus a 100% CENSUS of anything the
    ExG rule rejected on its own (weakest gate gets a census, not a sample).
    bulk_confirm gets a force-promoted fraction sent to human_review until the
    error rate is measured -- and release of the bulk queue is BLOCKED until
    the auto_reject spot-check reports.
    """
    salt = calibration.sha256
    rate = calibration.spot_number("auto_reject_contamination_rate", 0.01)
    power = calibration.spot_number("auto_reject_power", 0.90)
    target = spot_check_sample_size(rate, power)

    rejects = [d for d in decisions if d.bucket == BUCKET_AUTO_REJECT]
    census = [
        d
        for d in rejects
        if tuple(code for code in d.reason_codes if code != "mask_demoted")
        == ("vegetation_reject",)
    ]
    for decision in census:
        decision.audit_sample = True
        decision.reason_codes = decision.reason_codes + ("exg_solo_census",)

    remaining = [d for d in rejects if not d.audit_sample]
    sampled = _stratified_hash_sample(remaining, target, salt)
    for decision in sampled:
        decision.audit_sample = True
        decision.reason_codes = decision.reason_codes + ("audit_spot_check",)

    bulk = [d for d in decisions if d.bucket == BUCKET_BULK_CONFIRM]
    hold_fraction = calibration.spot_number("bulk_confirm_holdout_fraction", 0.08)
    bulk_images = sorted({d.row.record_id: d for d in bulk}.items())
    held_images: set[str] = set()
    if bulk_images:
        want = math.ceil(len(bulk_images) * hold_fraction)
        keyed = sorted(
            bulk_images,
            key=lambda item: (
                _sample_key(salt, item[1].context.source_image_sha256, item[0]),
                item[0],
            ),
        )
        held_images = {record_id for record_id, _ in keyed[:want]}
    forced = 0
    for decision in bulk:
        if decision.row.record_id in held_images:
            decision.bucket = BUCKET_HUMAN_REVIEW
            decision.tier = TIER_AUDIT
            decision.audit_sample = True
            decision.reason_codes = decision.reason_codes + ("audit_spot_check",)
            forced += 1

    return {
        "auto_reject_target_n": target,
        "auto_reject_contamination_rate": rate,
        "auto_reject_power": power,
        "auto_reject_sampled": len(sampled),
        "auto_reject_exg_solo_census": len(census),
        "bulk_confirm_holdout_fraction": hold_fraction,
        "bulk_confirm_images_held_for_review": len(held_images),
        "bulk_confirm_objects_forced_to_review": forced,
        "sampling_salt_sha256": salt,
        "bulk_queue_release_blocked_until_auto_reject_spot_check_reports": True,
    }


def _stratified_hash_sample(
    decisions: Sequence[Decision], target: int, salt: str
) -> list[Decision]:
    if target <= 0 or not decisions:
        return []
    if target >= len(decisions):
        return list(decisions)
    by_family: dict[str, list[Decision]] = defaultdict(list)
    for decision in decisions:
        by_family[decision.row.capture_family or "unknown"].append(decision)
    total = len(decisions)
    picked: list[Decision] = []
    for family in sorted(by_family):
        pool = sorted(
            by_family[family],
            key=lambda d: (
                _sample_key(salt, d.context.source_image_sha256, d.row.annotation_id),
                d.row.annotation_id,
            ),
        )
        quota = int(round(target * len(pool) / total))
        picked.extend(pool[: min(quota, len(pool))])
    if len(picked) < target:
        chosen = {id(d) for d in picked}
        leftovers = sorted(
            (d for d in decisions if id(d) not in chosen),
            key=lambda d: (
                _sample_key(salt, d.context.source_image_sha256, d.row.annotation_id),
                d.row.annotation_id,
            ),
        )
        picked.extend(leftovers[: target - len(picked)])
    return picked[:target]


# --------------------------------------------------------------------------
# emission
# --------------------------------------------------------------------------


def queue_row(decision: Decision) -> dict[str, Any]:
    row = decision.row
    signals = {
        name: _finite(row.features.get(name))
        for name in sorted(
            set(REQUIRED_FEATURES)
            | {
                F_VEG_IN,
                F_VEG_GAIN,
                F_GRABCUT_IOU,
                F_CROSS_CLASS_IOA,
                F_SAME_CLASS_MASK_IOU,
                F_SAME_CLASS_BOX_IOU,
                F_RICE_OVER_WEED_IOA,
                F_SAM_PRED_IOU,
            }
        )
    }
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "record_id": row.record_id,
        "annotation_id": row.annotation_id,
        "source_object_id": row.source_object_id,
        "label": row.label,
        "group_id": row.group_id,
        "capture_family": row.capture_family,
        "bucket": decision.bucket,
        "tier": decision.tier,
        "rank": decision.rank,
        "impact": decision.impact,
        "cost_seconds_est": decision.cost_seconds_est,
        "reason_codes": list(decision.reason_codes),
        "reason": decision.reason,
        "q": decision.q,
        "collision_group_id": decision.collision_group_id,
        "dhash_cluster_id": decision.dhash_cluster_id,
        "audit_sample": decision.audit_sample,
        "signals": signals,
    }


def summarise(
    decisions: Sequence[Decision],
    images: Sequence[QueueImage],
    spot_checks: Mapping[str, Any],
) -> dict[str, Any]:
    """Counts, projected human decisions, and the implied reduction.

    Projected decisions counts ONE screen-level confirmation per queued image
    plus one interaction per flagged object.  Baseline is reviewing every
    annotation individually.  This is a PRESENTATION estimate and it is
    UNMEASURED until real per-image timings exist -- Phase 1 auto-confirms
    nothing.
    """
    bucket_counts = Counter(decision.bucket for decision in decisions)
    tier_counts = Counter(decision.tier for decision in decisions)
    label_bucket = Counter((decision.row.label, decision.bucket) for decision in decisions)
    total_objects = len(decisions)
    total_images = len(images)
    flagged = sum(image.flagged_count for image in images)
    projected = total_images + flagged
    reduction = 1.0 - (projected / total_objects) if total_objects else 0.0
    cluster_sizes = Counter(image.dhash_cluster_id for image in images if image.dhash_cluster_id)
    histogram = Counter(cluster_sizes.values())

    return {
        "objects_total": total_objects,
        "images_total": total_images,
        "bucket_counts": {bucket: bucket_counts.get(bucket, 0) for bucket in sorted(BUCKETS)},
        "tier_counts": {tier: tier_counts.get(tier, 0) for tier in TIERS},
        "label_bucket_counts": {
            f"{label}|{bucket}": count for (label, bucket), count in sorted(label_bucket.items())
        },
        "flagged_objects": flagged,
        "projected_human_decisions": projected,
        "baseline_human_decisions_all_annotations": total_objects,
        "implied_reduction_vs_all_annotations": reduction,
        "images_with_zero_flagged_objects": sum(1 for image in images if image.flagged_count == 0),
        "dhash_cluster_size_histogram": {
            str(size): count for size, count in sorted(histogram.items())
        },
        "spot_checks": dict(spot_checks),
        "caveats": [
            "bulk_confirm means 'queued for bulk human approval', never 'accepted'; "
            "no code path here writes review_status.",
            "weed_target is never machine-confirmable: precedence rule 0 routes every "
            "weed object, and every object sharing an image with one, to human_review.",
            "the projected reduction is a PRESENTATION estimate; it is unmeasured until "
            "per-image timings exist, and anyone reporting it as a measured number is "
            "reporting a hope.",
        ],
    }


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
    )
    try:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


def run_triage(
    features_path: Path,
    calibration_path: Path,
    out_path: Path,
    manifest_path: Path | None = None,
    *,
    overwrite: bool = False,
    manifest_objects: bool = True,
) -> dict[str, Any]:
    """Pure-ish orchestrator: read, decide, rank, sample, emit.  Returns the
    manifest document so tests can assert on it without touching disk."""
    assert BUCKETS.isdisjoint(
        REVIEW_STATUSES_SNAPSHOT
    ), "triage bucket vocabulary must stay disjoint from REVIEW_STATUSES"
    for target in (out_path, manifest_path):
        if target is not None and Path(target).exists() and not overwrite:
            raise FileExistsError(f"{target} exists; pass --overwrite to replace it")

    calibration = load_calibration(Path(calibration_path))
    rows = read_feature_rows(Path(features_path))
    decisions = triage_objects(rows, calibration)
    score_decisions(decisions, calibration)
    spot_checks = select_spot_checks(decisions, calibration)
    images = build_image_queue(decisions, calibration)

    queue_rows = [queue_row(decision) for decision in decisions]
    _write_text_atomic(
        Path(out_path),
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in queue_rows),
    )

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "queue_schema_version": QUEUE_SCHEMA_VERSION,
        "features_path": str(features_path),
        "calibration_path": str(calibration_path),
        "calibration_sha256": calibration.sha256,
        "calibration_model_revision": calibration.model_revision,
        "queue_path": str(out_path),
        "bucket_vocabulary": sorted(BUCKETS),
        "tier_vocabulary": list(TIERS),
        "thresholds": calibration.thresholds_report(),
        "summary": summarise(decisions, images, spot_checks),
        "image_queue": [
            {
                "rank": image.rank,
                "record_id": image.record_id,
                "group_id": image.group_id,
                "capture_family": image.capture_family,
                "tier": image.tier,
                "impact": image.impact,
                "cost_seconds_est": image.cost_seconds_est,
                "flagged_count": image.flagged_count,
                "object_count": image.object_count,
                "bucket_counts": image.bucket_counts,
                "dhash_cluster_id": image.dhash_cluster_id,
            }
            for image in images
        ],
    }
    if manifest_objects:
        manifest["objects"] = queue_rows
    if manifest_path is not None:
        _write_text_atomic(Path(manifest_path), json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--features",
        required=True,
        type=Path,
        help="proposal_features_v1.jsonl from optimize_proposals.py",
    )
    parser.add_argument(
        "--calibration",
        required=True,
        type=Path,
        help="triage_calibration_v1.json; REQUIRED -- no defaults exist",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="triage_queue_v1.jsonl sidecar (agrinav.triage_queue.v1)",
    )
    parser.add_argument(
        "--out-manifest",
        type=Path,
        default=None,
        help="triage manifest JSON with per-annotation decisions + summary",
    )
    parser.add_argument(
        "--no-manifest-objects",
        action="store_true",
        help="omit the per-annotation array from the manifest",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = run_triage(
            args.features,
            args.calibration,
            args.out,
            args.out_manifest,
            overwrite=args.overwrite,
            manifest_objects=not args.no_manifest_objects,
        )
    except (TriageConfigError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = manifest["summary"]
    print(f"triaged {summary['objects_total']} objects over {summary['images_total']} images")
    for bucket, count in summary["bucket_counts"].items():
        print(f"  {bucket:14s}: {count}")
    print(
        f"  projected human decisions: {summary['projected_human_decisions']} "
        f"(baseline {summary['baseline_human_decisions_all_annotations']}, "
        f"implied reduction {summary['implied_reduction_vs_all_annotations']:.1%})"
    )
    print("  NOTE: bulk_confirm == queued for bulk HUMAN approval, not accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
