#!/usr/bin/env python3
"""SAM2.1 box->mask refinement over the UNREVIEWED COCO proposal layer.

WHY THIS SCRIPT IS DELIBERATELY DUMB
------------------------------------
This robot sprays or cuts whatever ends up labelled ``weed_target``. A rice
seedling mislabelled as weed is destroyed crop, so the safety argument here is
structural, not statistical:

* SAM is allowed to change **geometry only**. The label is copied from the
  human COCO box through a *closed* dict with an explicit counted drop. There
  is no ``else`` branch and no ``dict.get(..., default_label)`` anywhere in the
  mapping — that is the exact shape of the quarantined bug in
  ``_archive/unsafe_inference/auto_annotate.py`` (every detection normalised to
  one class).
* SAM is prompted with the **human box only**. Text prompts are forbidden:
  ``"weeds growing among the rice plants"`` over a flooded paddy segments
  duckweed mats and specular reflections and then *inherits* ``weed_target``
  from the prompt, inventing target objects no human ever drew
  (ontology forbidden_inference 3).
* This stage emits a **raw candidate sidecar and NO annotation records**. Every
  safety-relevant predicate (mask acceptance, demotion, triage) lives
  downstream in CPU-only code so it can be unit-tested on a laptop with no GPU,
  no checkpoint and no archive. A safety invariant that only runs inside a
  Colab notebook is an untested invariant.
* Nothing here can produce truth. There is no code path that writes
  ``review_status`` ``"accepted"``/``"adjudicated"``, a non-null
  ``verified_empty``, a non-null ``treatment_eligible``, or a non-null
  ``annotator_id``/``reviewer_id``.

PREFLIGHT IS A HARD BLOCKER (fail closed, before any GPU allocation)
--------------------------------------------------------------------
1. ``--model-revision`` must be a real immutable commit (``^[0-9a-f]{7,40}$``).
   ``configs/annotation/pilot_v1.json`` ships the literal ``PIN_BEFORE_RUN``,
   and ``scripts/validate_annotation_package.py`` only checks that the revision
   is a non-empty *string* — so an unpinned run produces provenance that
   validates perfectly clean and is unrecoverable. We refuse instead.
2. Every proposal image must have a non-null sha256 and width/height, the zip
   bytes must hash to that sha256, and the *decoded* image size must equal the
   recorded width/height. We never substitute ``"0"*64`` or ``width=1``: an
   invalid ``source.width`` ZEROES the dimension downstream and SKIPS ALL
   geometry validation for that record
   (``scripts/validate_annotation_package.py:493-494``).

COST MODEL
----------
Median 27 boxes/image over 1347 images. The image embedding is computed ONCE
per image and amortised over its boxes; a naive per-box ``set_image()`` is ~27x
the cost and will not finish a Colab session. Per box we run 8 decoder-only
passes: 3 ``multimask_output`` candidates on the exact human box, plus K=5
deterministic box jitters (each edge perturbed +/-3% of the box w/h, seeded by
``sha256(image_sha|source_object_id|k)`` so the jitter agreement statistic is
reproducible and cannot be reshuffled by re-running).

CLI (driven from notebooks/sam_box_to_mask_colab.ipynb as a thin driver):

    python -m agrinav.data.sam_box_to_mask \
        --coco-zip <coco_export>.v1i.coco.zip \
        --proposals-json artifacts/detector_v1/coco_proposals_unreviewed.coco.json \
        --model-id facebook/sam2.1-hiera-large \
        --model-revision <40-hex-commit> \
        --out-shard artifacts/detector_v1/sam_raw/shard_%03d.jsonl \
        --shard-index 0 --shard-count 8

Local CPU tests inject a fake predictor:

    --predictor-factory tests.test_sam_box_to_mask:make_stub_predictor
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol, Sequence

import numpy as np

RAW_SCHEMA_VERSION = "agrinav.sam_raw_candidates.v1"

#: rice_detection COCO category id -> canonical ontology label. CLOSED dict.
#: No ``else``, no ``.get(..., default)``. Unmapped ids are counted and dropped
#: and (unless explicitly acknowledged) abort the run.
COCO_CATEGORY_TO_LABEL: dict[int, str] = {1: "rice_protect", 2: "weed_target"}

#: The only prompt modality this pipeline may use. Recorded verbatim into
#: provenance.prompt so the artifact states on its face that no text was used.
BOX_PROMPT = "box_prompt:coco_human_box"

#: Any of these reaching the predictor would let the model invent an object
#: identity that no human asserted.
FORBIDDEN_PREDICT_KWARGS = frozenset(
    {"text", "text_prompt", "label", "labels", "class_name", "phrase", "caption"}
)

REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")
PLACEHOLDER_REVISIONS = frozenset(
    {"", "pin_before_run", "todo", "changeme", "latest", "main", "master", "head", "none"}
)

MULTIMASK_CANDIDATES = 3
JITTER_CANDIDATES = 5
JITTER_FRACTION = 0.03


class SamPreflightError(Exception):
    """Raised when the run is not safe to start. Always fatal."""


class BoxPredictor(Protocol):
    """The narrow slice of the SAM2.1 ``SAM2ImagePredictor`` API we depend on.

    Deliberately minimal so a synthetic CPU stub is a faithful substitute.
    """

    def set_image(self, image: np.ndarray) -> None: ...

    def predict(
        self, *, box: np.ndarray, multimask_output: bool
    ) -> tuple[np.ndarray, np.ndarray, Any]: ...


# --------------------------------------------------------------------------
# pure core: preflight
# --------------------------------------------------------------------------


def validate_model_revision(revision: str | None) -> str:
    """Return the pinned revision, or raise ``SamPreflightError``.

    Fail closed. ``PIN_BEFORE_RUN`` (live in configs/annotation/pilot_v1.json)
    passes the package validator's non-emptiness check, so it must be rejected
    here — before any GPU allocation, any model download, any image read.
    """
    if revision is None:
        raise SamPreflightError(
            "--model-revision is required and must be a pinned immutable commit "
            "matching ^[0-9a-f]{7,40}$ (refusing to silently use HEAD)"
        )
    candidate = revision.strip()
    if candidate.casefold() in PLACEHOLDER_REVISIONS:
        raise SamPreflightError(
            f"--model-revision {revision!r} is a placeholder, not a pinned revision. "
            "Resolve the model repo commit sha first; unpinned provenance validates "
            "clean and is unrecoverable."
        )
    if not REVISION_RE.match(candidate):
        raise SamPreflightError(
            f"--model-revision {revision!r} does not match ^[0-9a-f]{{7,40}}$; "
            "pass a real commit sha, not a tag or branch name."
        )
    return candidate


def map_category(category_id: int) -> str | None:
    """Closed-dict label lookup. Returns ``None`` for an unmapped category.

    A ``None`` here is a *counted drop*, never a default label.
    """
    return COCO_CATEGORY_TO_LABEL.get(category_id)


def clip_box(
    bbox: Sequence[float], width: int, height: int
) -> tuple[float, float, float, float] | None:
    """Clip a COCO ``[x, y, w, h]`` box to the image. ``None`` if degenerate.

    The upstream converter copies Roboflow boxes verbatim with no bounds check,
    and the package validator rejects a box strictly at the edge.
    """
    x, y, w, h = (float(v) for v in bbox)
    x0, y0 = max(0.0, x), max(0.0, y)
    x1, y1 = min(float(width), x + w), min(float(height), y + h)
    if not (x1 > x0 and y1 > y0):
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _deterministic_unit(*parts: object) -> Iterator[float]:
    """Yield reproducible floats in [-1, 1] from a content-addressed seed.

    Content-addressed rather than ``random.random()`` so that re-running the
    pipeline cannot reshuffle the jitter set (and therefore cannot reshuffle the
    downstream jitter-agreement statistic).
    """
    material = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    for i in range(0, len(digest), 8):
        chunk = digest[i : i + 8]
        if len(chunk) < 8:
            return
        yield (int(chunk, 16) / 0xFFFFFFFF) * 2.0 - 1.0


def jitter_box(
    bbox: Sequence[float],
    image_sha: str,
    source_object_id: str,
    k: int,
    width: int,
    height: int,
    fraction: float = JITTER_FRACTION,
) -> tuple[float, float, float, float] | None:
    """Perturb each edge by +/- ``fraction`` of the box w/h, deterministically."""
    x, y, w, h = (float(v) for v in bbox)
    draws = list(_deterministic_unit(image_sha, source_object_id, k))[:4]
    if len(draws) < 4:  # pragma: no cover - sha256 always yields 8 chunks
        raise SamPreflightError("insufficient deterministic draws for jitter")
    dx0, dy0, dx1, dy1 = draws
    x0 = x + dx0 * fraction * w
    y0 = y + dy0 * fraction * h
    x1 = x + w + dx1 * fraction * w
    y1 = y + h + dy1 * fraction * h
    if x1 <= x0 or y1 <= y0:
        return None
    return clip_box((x0, y0, x1 - x0, y1 - y0), width, height)


def xywh_to_xyxy(bbox: Sequence[float]) -> list[float]:
    x, y, w, h = (float(v) for v in bbox)
    return [x, y, x + w, y + h]


def encode_mask_rle(mask: np.ndarray) -> dict[str, Any]:
    """Encode a HxW boolean mask as a COCO RLE with ``size=[height, width]``.

    ``counts`` is ``.decode('ascii')`` because pycocotools returns bytes and the
    package validator rejects bytes with a message that does not hint at the
    type problem. ``size`` is [height, width] — the OPPOSITE order of the
    ``bbox`` [x, y, w, h] convention used a few lines away.
    """
    from pycocotools import mask as maskutils  # local import: optional at import time

    arr = np.asfortranarray(np.asarray(mask).astype(np.uint8))
    if arr.ndim != 2:
        raise ValueError(f"mask must be 2-D HxW, got shape {arr.shape}")
    encoded = maskutils.encode(arr)
    counts = encoded["counts"]
    if isinstance(counts, bytes):
        counts = counts.decode("ascii")
    height, width = arr.shape
    return {"size": [int(height), int(width)], "counts": counts}


def mask_pixel_area(mask: np.ndarray) -> int:
    return int(np.count_nonzero(np.asarray(mask)))


def build_provenance(
    model_id: str,
    model_revision: str,
    thresholds: dict[str, Any],
    source_image_sha256: str,
    generated_at: str,
) -> dict[str, Any]:
    """The ontology's ``proposal_provenance_required`` block, explicit nulls.

    ``original_proposal`` is filled in by the caller with the immutable raw
    model output. ``review_status`` is ``"unreviewed"`` — the value in the
    annotation_record.v1 enum. (The COCO proposal layer's ``unreviewed_proposal``
    is a different, non-enum vocabulary; carrying it forward would poison every
    downstream record.)
    """
    return {
        "proposal_model_id": model_id,
        "proposal_model_revision": model_revision,
        "proposal_method": "model_assisted",
        "prompt": BOX_PROMPT,
        "thresholds": dict(thresholds),
        "source_image_sha256": source_image_sha256,
        "generated_at": generated_at,
        "original_proposal": None,
        "human_edit_state": "unreviewed",
        "annotator_id": None,
        "reviewer_id": None,
        "review_status": "unreviewed",
    }


def run_thresholds(
    shard_index: int, shard_count: int, jitter_fraction: float = JITTER_FRACTION
) -> dict[str, Any]:
    """Non-empty thresholds dict. This stage FITS NOTHING; these are run params."""
    return {
        "multimask_output": True,
        "multimask_candidates": MULTIMASK_CANDIDATES,
        "jitter_candidates": JITTER_CANDIDATES,
        "jitter_fraction": jitter_fraction,
        "candidate_selection": "deferred_to_optimize_proposals",
        "mask_score_threshold": None,
        "shard_index": shard_index,
        "shard_count": shard_count,
    }


def raw_key(source_image_sha256: str, source_object_id: str) -> str:
    return f"{source_image_sha256}|{source_object_id}"


def shard_of(image_key: str, shard_count: int) -> int:
    """Content-addressed shard assignment: stable under corpus changes."""
    if shard_count <= 1:
        return 0
    return int(hashlib.sha256(image_key.encode("utf-8")).hexdigest()[:8], 16) % shard_count


# --------------------------------------------------------------------------
# pure core: proposal indexing
# --------------------------------------------------------------------------


def index_proposals(doc: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Group the COCO proposal doc into per-image work units.

    Returns ``(units, drops)``. ``drops`` counts unmapped category ids by id —
    an explicit counter, because a silent ``continue`` is how boxes vanish.
    """
    by_image: dict[int, dict[str, Any]] = {}
    for image in doc.get("images", []):
        by_image[image["id"]] = {
            "coco_image_id": image["id"],
            "file_name": image.get("file_name"),
            "width": image.get("width"),
            "height": image.get("height"),
            "sha256": image.get("sha256"),
            "group_id": image.get("group_id"),
            "capture_family": image.get("capture_family"),
            "boxes": [],
        }
    drops: dict[str, int] = {}
    for ann in doc.get("annotations", []):
        label = map_category(ann["category_id"])
        if label is None:
            key = f"category_id={ann['category_id']}"
            drops[key] = drops.get(key, 0) + 1
            continue
        unit = by_image.get(ann["image_id"])
        if unit is None:
            key = "orphan_annotation_missing_image"
            drops[key] = drops.get(key, 0) + 1
            continue
        unit["boxes"].append(
            {
                "source_object_id": f"coco-ann-{ann['id']}",
                "coco_annotation_id": ann["id"],
                "category_id": ann["category_id"],
                "label": label,
                "bbox": [float(v) for v in ann["bbox"]],
            }
        )
    units = [by_image[k] for k in sorted(by_image)]
    return units, drops


def preflight_image(unit: dict[str, Any], raw_bytes: bytes) -> np.ndarray:
    """Verify hash + declared size against the real bytes; return RGB array.

    Never substitutes a placeholder. A wrong ``width`` downstream silently
    suppresses every geometry error in the record.
    """
    from PIL import Image  # local import so the module imports without Pillow

    name = unit.get("file_name")
    recorded = unit.get("sha256")
    if not isinstance(recorded, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", recorded):
        raise SamPreflightError(f"{name}: proposal sha256 is missing or malformed ({recorded!r})")
    actual = hashlib.sha256(raw_bytes).hexdigest().lower()
    if actual != recorded.lower():
        raise SamPreflightError(
            f"{name}: sha256 mismatch (recorded {recorded.lower()}, archive {actual})"
        )
    width, height = unit.get("width"), unit.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise SamPreflightError(f"{name}: width/height missing or non-positive ({width}x{height})")
    with Image.open(io.BytesIO(raw_bytes)) as im:
        if im.size != (width, height):
            raise SamPreflightError(
                f"{name}: decoded size {im.size} != recorded ({width}, {height})"
            )
        return np.asarray(im.convert("RGB"))


# --------------------------------------------------------------------------
# pure core: per-image inference
# --------------------------------------------------------------------------


def _predict_box(
    predictor: BoxPredictor, box_xywh: Sequence[float], multimask_output: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Call the predictor with a BOX ONLY. Structurally incapable of text."""
    kwargs: dict[str, Any] = {
        "box": np.asarray(xywh_to_xyxy(box_xywh), dtype=np.float32),
        "multimask_output": bool(multimask_output),
    }
    forbidden = FORBIDDEN_PREDICT_KWARGS & set(kwargs)
    if forbidden:  # pragma: no cover - defensive; kwargs is a literal above
        raise SamPreflightError(f"text-style prompt kwargs are forbidden: {sorted(forbidden)}")
    masks, scores, _ = predictor.predict(**kwargs)
    masks = np.asarray(masks)
    if masks.ndim == 2:
        masks = masks[None, ...]
    scores = np.asarray(scores).reshape(-1)
    return masks, scores


def candidates_for_box(
    predictor: BoxPredictor,
    box: dict[str, Any],
    width: int,
    height: int,
    image_sha: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Produce the 8 raw candidates for one human box.

    Returns ``(candidates, degenerate_reason)``. A box that cannot be clipped to
    a positive-area rectangle yields ``([], reason)`` — the object is still
    EMITTED by the caller (with zero candidates) so that downstream code demotes
    it to bbox geometry rather than deleting a human assertion.
    """
    clipped = clip_box(box["bbox"], width, height)
    if clipped is None:
        return [], "prompt_box_degenerate_after_clip"

    candidates: list[dict[str, Any]] = []
    masks, scores = _predict_box(predictor, clipped, multimask_output=True)
    for i in range(min(MULTIMASK_CANDIDATES, masks.shape[0])):
        mask = masks[i].astype(bool)
        candidates.append(
            {
                "candidate_index": len(candidates),
                "kind": "multimask",
                "multimask_index": i,
                "jitter_index": None,
                "prompt_box": list(clipped),
                "sam_pred_iou": float(scores[i]) if i < scores.size else None,
                "area_px": mask_pixel_area(mask),
                "rle": encode_mask_rle(mask),
            }
        )

    for k in range(JITTER_CANDIDATES):
        jittered = jitter_box(clipped, image_sha, box["source_object_id"], k, width, height)
        if jittered is None:
            continue
        jmasks, jscores = _predict_box(predictor, jittered, multimask_output=False)
        mask = jmasks[0].astype(bool)
        candidates.append(
            {
                "candidate_index": len(candidates),
                "kind": "jitter",
                "multimask_index": None,
                "jitter_index": k,
                "prompt_box": list(jittered),
                "sam_pred_iou": float(jscores[0]) if jscores.size else None,
                "area_px": mask_pixel_area(mask),
                "rle": encode_mask_rle(mask),
            }
        )
    return candidates, None


def rows_for_image(
    predictor: BoxPredictor,
    unit: dict[str, Any],
    image: np.ndarray,
    provenance_template: dict[str, Any],
) -> list[dict[str, Any]]:
    """Encode once, decode per box. One output row per input box, always."""
    height, width = int(unit["height"]), int(unit["width"])
    image_sha = str(unit["sha256"]).lower()
    predictor.set_image(image)

    rows: list[dict[str, Any]] = []
    for box in unit["boxes"]:
        candidates, reason = candidates_for_box(predictor, box, width, height, image_sha)
        provenance = dict(provenance_template)
        provenance["source_image_sha256"] = image_sha
        provenance["original_proposal"] = {
            "source_object_id": box["source_object_id"],
            "coco_annotation_id": box["coco_annotation_id"],
            "coco_category_id": box["category_id"],
            "coco_bbox_xywh": list(box["bbox"]),
            "candidates": candidates,
        }
        rows.append(
            {
                "schema_version": RAW_SCHEMA_VERSION,
                "key": raw_key(image_sha, box["source_object_id"]),
                "source_image_sha256": image_sha,
                "coco_image_id": unit["coco_image_id"],
                "file_name": unit["file_name"],
                "width": width,
                "height": height,
                "group_id": unit.get("group_id"),
                "capture_family": unit.get("capture_family"),
                "source_object_id": box["source_object_id"],
                "coco_annotation_id": box["coco_annotation_id"],
                "label": box["label"],
                "prompt_box_clipped": (list(clip_box(box["bbox"], width, height) or [])),
                "degenerate_reason": reason,
                "candidate_count": len(candidates),
                "provenance": provenance,
            }
        )
    return rows


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------


def load_done_keys(shard_dir: Path) -> set[str]:
    """Resume support: keys already present in any existing shard file."""
    done: set[str] = set()
    if not shard_dir.exists():
        return done
    for path in sorted(shard_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # truncated tail from a killed Colab session
                key = row.get("key")
                if isinstance(key, str):
                    done.add(key)
    return done


def append_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_predictor_factory(spec: str) -> Callable[[], BoxPredictor]:
    """Resolve ``module:attr`` to a zero-arg factory returning a predictor."""
    if ":" not in spec:
        raise SamPreflightError(f"--predictor-factory {spec!r} must be 'module:attr'")
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, attr)
    if not callable(factory):
        raise SamPreflightError(f"--predictor-factory {spec!r} is not callable")
    return factory


def default_predictor_factory(model_id: str, revision: str) -> Callable[[], BoxPredictor]:
    """Build the real SAM2.1 predictor. Imported lazily — never at module import.

    This is the only place that would touch a GPU or download a checkpoint, and
    it is unreachable from the unit tests (which always inject a stub).
    """

    def _factory() -> BoxPredictor:  # pragma: no cover - requires GPU + network
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        return SAM2ImagePredictor.from_pretrained(model_id, revision=revision)

    return _factory


def process(
    *,
    zip_path: Path,
    proposals: dict[str, Any],
    predictor_factory: Callable[[], BoxPredictor],
    out_shard: str,
    shard_index: int,
    shard_count: int,
    model_id: str,
    model_revision: str,
    allow_unmapped_categories: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run the shard. Preflight everything before the predictor is constructed."""
    if shard_count < 1 or not (0 <= shard_index < shard_count):
        raise SamPreflightError(f"invalid sharding: index {shard_index} of count {shard_count}")

    units, drops = index_proposals(proposals)
    if drops and not allow_unmapped_categories:
        raise SamPreflightError(
            f"unmapped/orphan COCO annotations {drops}; these would be silently "
            "dropped. Re-run with --allow-unmapped-categories only after the "
            "affected images are routed to human review."
        )

    mine = [
        u
        for u in units
        if shard_of(f"{u['coco_image_id']}|{u['file_name']}", shard_count) == shard_index
    ]

    out_path = Path(out_shard % shard_index if "%" in out_shard else out_shard)
    done = load_done_keys(out_path.parent)

    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    template = build_provenance(
        model_id=model_id,
        model_revision=model_revision,
        thresholds=run_thresholds(shard_index, shard_count),
        source_image_sha256="",
        generated_at=stamp,
    )

    # Preflight pass: verify EVERY image in this shard before any model work.
    verified: list[tuple[dict[str, Any], np.ndarray]] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for unit in mine:
            verified.append((unit, preflight_image(unit, archive.read(unit["file_name"]))))

    predictor = predictor_factory()

    stats = {
        "images_in_shard": len(mine),
        "images_processed": 0,
        "images_skipped_resume": 0,
        "boxes_emitted": 0,
        "boxes_degenerate": 0,
        "candidates_emitted": 0,
        "unmapped_dropped": sum(drops.values()),
        "labels": {},
    }
    for unit, image in verified:
        pending = [
            b
            for b in unit["boxes"]
            if raw_key(str(unit["sha256"]).lower(), b["source_object_id"]) not in done
        ]
        if not pending:
            stats["images_skipped_resume"] += 1
            continue
        work_unit = dict(unit)
        work_unit["boxes"] = pending
        rows = rows_for_image(predictor, work_unit, image, template)
        append_rows(out_path, rows)
        stats["images_processed"] += 1
        stats["boxes_emitted"] += len(rows)
        for row in rows:
            stats["candidates_emitted"] += row["candidate_count"]
            if row["degenerate_reason"] is not None:
                stats["boxes_degenerate"] += 1
            stats["labels"][row["label"]] = stats["labels"].get(row["label"], 0) + 1
    stats["out_shard"] = str(out_path)
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SAM2.1 box->mask raw candidate generation")
    ap.add_argument("--coco-zip", required=True, type=Path)
    ap.add_argument("--proposals-json", required=True, type=Path)
    ap.add_argument("--model-id", default="facebook/sam2.1-hiera-large")
    ap.add_argument(
        "--model-revision",
        required=True,
        help="pinned immutable commit sha (^[0-9a-f]{7,40}$). 'PIN_BEFORE_RUN' is refused.",
    )
    ap.add_argument(
        "--out-shard", required=True, help="path or printf pattern, e.g. shard_%%03d.jsonl"
    )
    ap.add_argument("--shard-index", type=int, default=0)
    ap.add_argument("--shard-count", type=int, default=1)
    ap.add_argument(
        "--predictor-factory",
        default=None,
        help="test-only injection point, 'module:attr' returning a predictor",
    )
    ap.add_argument("--allow-unmapped-categories", action="store_true")
    args = ap.parse_args(argv)

    try:
        # 1. Revision preflight FIRST: before any zip read, any model load.
        revision = validate_model_revision(args.model_revision)
        proposals = json.loads(args.proposals_json.read_text(encoding="utf-8"))
        factory = (
            load_predictor_factory(args.predictor_factory)
            if args.predictor_factory
            else default_predictor_factory(args.model_id, revision)
        )
        stats = process(
            zip_path=args.coco_zip,
            proposals=proposals,
            predictor_factory=factory,
            out_shard=args.out_shard,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            model_id=args.model_id,
            model_revision=revision,
            allow_unmapped_categories=args.allow_unmapped_categories,
        )
    except SamPreflightError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print("Wrote RAW SAM candidates (NOT annotation records, NOT training truth)")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
