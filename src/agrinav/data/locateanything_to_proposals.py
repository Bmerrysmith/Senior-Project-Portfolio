#!/usr/bin/env python3
"""Zero-shot open-vocabulary boxes -> the UNREVIEWED COCO proposal layer.

WHERE THIS SITS IN THE PIPELINE
-------------------------------
This is the *front door* of the automated annotation pipeline described in
``docs/annotation_guide.md`` §8 and ``configs/annotation/pilot_v1.json``::

    (this script)  LocateAnything / open-vocab boxes  --->  COCO proposals
    scripts/sam_box_to_mask.py    boxes -> SAM2.1 masks --->  raw candidates
    scripts/triage_proposals.py   route to human review buckets
    <<< HUMAN REVIEW is the only thing that mints ground truth >>>
    scripts/export_yolo_dataset.py  accepted records -> YOLOv8/v11 dataset

``scripts/coco_boxes_to_proposals.py`` already turns *pre-existing human* COCO
boxes into proposals. This script covers the other case the annotation guide
needs: generating boxes on **unlabelled** images with an open-vocabulary model
(LocateAnything-3B, Grounding DINO, ...) so a large corpus can be bootstrapped
without hand-drawing every seed box.

WHY IT IS DELIBERATELY DUMB (same safety shape as sam_box_to_mask.py)
--------------------------------------------------------------------
This project's robot sprays or cuts whatever is finally labelled
``weed_target``.  The single most dangerous bug in an auto-labeller is the one
quarantined in ``_archive/unsafe_inference/auto_annotate.py``: normalising every
generic ``plant`` detection to one class.  So here:

* A *prompt* is mapped to an ontology category through a **closed** dict with
  an explicit counted drop.  There is no ``else`` branch and no
  ``dict.get(..., default_label)``.  An unmapped prompt is dropped and counted,
  never silently coerced to rice or weed.
* Ambiguous prompts map to ``unknown_vegetation`` (id 3), never to rice.
  "not rice" is never a target; that is a forbidden inference in
  ``data/ontology.v1.json``.
* Every emitted annotation is ``review_status="unreviewed_proposal"`` and
  carries full proposal provenance (model id, pinned revision, prompt,
  thresholds, generation time, original box).  It is NOT training truth.

The heavy model is never imported at module load and never downloaded by the
self-test.  Real runs need a GPU/WSL/Colab environment and accepted model
licences (see ``docs/research/PERCEPTION_RESEARCH_PACKAGE_2026-07-20.md``);
tests inject a fake generator.

Usage (real run, on a GPU box with licences accepted)::

    python -m agrinav.data.locateanything_to_proposals \
        --images-dir data/rice_training_curated/aerial \
        --model-id nvidia/LocateAnything-3B \
        --model-revision <pinned-commit-sha> \
        --out-json artifacts/annotation/locateanything_proposals_unreviewed.coco.json

Contract check (no model, no network)::

    python -m agrinav.data.locateanything_to_proposals --self-test
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence, runtime_checkable

# --------------------------------------------------------------------------
# ontology (kept local + closed, matching scripts/sam_box_to_mask.py style)
# --------------------------------------------------------------------------

#: canonical ontology id -> label name (data/ontology.v1.json canonical_labels)
CANONICAL_ID_TO_LABEL: dict[int, str] = {
    1: "rice_protect",
    2: "weed_target",
    3: "unknown_vegetation",
    4: "non_target_aquatic",
    5: "ground_exclusion",
}

#: Which canonical categories the downstream box->mask refiner
#: (scripts/sam_box_to_mask.py) currently accepts. Others are still emitted as
#: proposals but will be *counted drops* at the SAM step until a semantic-mask /
#: SAM3-text path handles them. Documented so nobody is surprised by the drop.
SAM_BOX_REFINABLE_IDS = frozenset({1, 2})

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

# The default prompt map mirrors the "locateanything_sam21" method in
# configs/annotation/pilot_v1.json. Each prompt is deliberately, explicitly
# mapped to ONE canonical category. Ambiguous vegetation -> unknown_vegetation,
# never rice. This dict is the whole safety story: keep it closed.
DEFAULT_PROMPT_MAP: dict[str, int] = {
    "cultivated rice plants": 1,
    "weeds growing among the rice plants": 2,
    "ambiguous vegetation that may not be rice": 3,
}


class ProposalError(RuntimeError):
    """Preflight/contract failure. Fatal: never degrade to a placeholder."""


# --------------------------------------------------------------------------
# generator injection point
# --------------------------------------------------------------------------


@runtime_checkable
class BoxGenerator(Protocol):
    """Open-vocabulary detector wrapper.

    ``generate`` returns a list of raw detections for one image. Each detection
    is a dict with keys ``prompt`` (str, must be one of the prompts passed in),
    ``bbox`` ([x, y, w, h] in pixels), and ``score`` (float in [0, 1] or None).
    The wrapper does NOT know about ontology categories; mapping prompt ->
    category happens here, through a closed dict.
    """

    def generate(
        self, image: "Any", prompts: Sequence[str]
    ) -> list[dict[str, Any]]:  # pragma: no cover - Protocol
        ...


def load_generator_factory(spec: str) -> Callable[[], BoxGenerator]:
    """Resolve ``module:attr`` to a zero-arg factory returning a BoxGenerator."""
    if ":" not in spec:
        raise ProposalError(f"--generator-factory {spec!r} must be 'module:attr'")
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, attr)
    if not callable(factory):
        raise ProposalError(f"--generator-factory {spec!r} is not callable")
    return factory


def default_generator_factory(model_id: str, revision: str) -> Callable[[], BoxGenerator]:
    """Real backend. Requires a GPU environment + accepted model licence.

    Kept behind a factory so importing this module never pulls torch or
    downloads 7.8 GB of weights. Left unimplemented on purpose: wiring a
    specific open-vocab model is an environment decision, not a library one.
    """

    def _factory() -> BoxGenerator:  # pragma: no cover - requires GPU + network
        raise ProposalError(
            "No default open-vocabulary backend is wired in. Provide one with "
            "--generator-factory module:attr (e.g. a LocateAnything or "
            "Grounding DINO wrapper) in a GPU/WSL/Colab environment with the "
            f"model licence for {model_id!r} @ {revision} accepted. See "
            "docs/research/PERCEPTION_RESEARCH_PACKAGE_2026-07-20.md."
        )

    return _factory


# --------------------------------------------------------------------------
# pure helpers
# --------------------------------------------------------------------------


def validate_model_revision(revision: str) -> str:
    """Refuse the placeholder; require a pinned immutable ref (like SAM step)."""
    if revision == "PIN_BEFORE_RUN":
        raise ProposalError(
            "--model-revision is still 'PIN_BEFORE_RUN'. Pin the immutable "
            "commit sha of the model before generating proposals."
        )
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", revision):
        raise ProposalError(f"--model-revision {revision!r} must be a 7-40 char commit sha.")
    return revision.lower()


def build_prompt_map(spec: str | None) -> dict[str, int]:
    """Parse an optional 'prompt=cat_id;prompt=cat_id' override, else default.

    Every category id must exist in the ontology. This stays a closed dict.
    """
    if spec is None:
        return dict(DEFAULT_PROMPT_MAP)
    mapping: dict[str, int] = {}
    for pair in spec.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ProposalError(f"--prompt-map entry {pair!r} must be 'prompt=cat_id'")
        prompt, raw_id = pair.rsplit("=", 1)
        prompt = prompt.strip()
        try:
            cat_id = int(raw_id)
        except ValueError as exc:
            raise ProposalError(f"--prompt-map id in {pair!r} is not an int") from exc
        if cat_id not in CANONICAL_ID_TO_LABEL:
            raise ProposalError(
                f"--prompt-map category id {cat_id} is not an ontology id "
                f"(valid: {sorted(CANONICAL_ID_TO_LABEL)})"
            )
        mapping[prompt] = cat_id
    if not mapping:
        raise ProposalError("--prompt-map produced an empty map")
    return mapping


def clip_box(
    bbox: Sequence[float], width: int, height: int
) -> tuple[float, float, float, float] | None:
    """Clip [x, y, w, h] to the image; return None for non-positive area."""
    x, y, w, h = (float(v) for v in bbox)
    x0 = max(0.0, min(x, float(width)))
    y0 = max(0.0, min(y, float(height)))
    x1 = max(0.0, min(x + w, float(width)))
    y1 = max(0.0, min(y + h, float(height)))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def iter_image_paths(images_dir: Path) -> list[Path]:
    return sorted(
        p for p in images_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def probe_image(path: Path) -> tuple[str, int, int]:
    """Return (sha256, width, height) for one image file. Requires Pillow."""
    from PIL import Image  # local import so the module imports without Pillow

    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest().lower()
    with Image.open(path) as im:
        width, height = im.size
    return sha, int(width), int(height)


def load_image_array(path: Path) -> Any:
    """Return an RGB ndarray for the generator. Requires Pillow + numpy."""
    import numpy as np
    from PIL import Image

    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


# --------------------------------------------------------------------------
# pure core: detections -> COCO proposal doc
# --------------------------------------------------------------------------


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_proposal_doc(
    *,
    image_units: list[dict[str, Any]],
    prompt_map: dict[str, int],
    model_id: str,
    model_revision: str,
    score_threshold: float,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Turn per-image detections into the COCO proposal doc + a stats dict.

    ``image_units`` items:
      {file_name, sha256, width, height, group_id, capture_family, detections}
    where each detection is {prompt, bbox:[x,y,w,h], score}.

    Output matches the doc consumed by scripts/sam_box_to_mask.py:
      images[]: id, file_name, width, height, sha256, group_id, capture_family,
                review_status
      annotations[]: id, image_id, category_id, bbox, review_status, provenance
      categories[]: canonical id -> name
    """
    generated_at = generated_at or _now_iso()
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    drops: dict[str, int] = {}
    per_category: dict[str, int] = {}
    next_ann_id = 1

    for image_id, unit in enumerate(image_units, start=1):
        width = int(unit["width"])
        height = int(unit["height"])
        images.append(
            {
                "id": image_id,
                "file_name": unit["file_name"],
                "width": width,
                "height": height,
                "sha256": str(unit["sha256"]).lower(),
                "group_id": unit.get("group_id"),
                "capture_family": unit.get("capture_family"),
                "review_status": "unreviewed_proposal",
            }
        )
        for det in unit.get("detections", []):
            prompt = det.get("prompt")
            # CLOSED map. Unknown prompt -> counted drop, never a default label.
            cat_id = prompt_map.get(prompt) if isinstance(prompt, str) else None
            if cat_id is None:
                drops[f"unmapped_prompt={prompt!r}"] = (
                    drops.get(f"unmapped_prompt={prompt!r}", 0) + 1
                )
                continue
            score = det.get("score")
            if score is not None and float(score) < score_threshold:
                drops["below_score_threshold"] = drops.get("below_score_threshold", 0) + 1
                continue
            clipped = clip_box(det["bbox"], width, height)
            if clipped is None:
                drops["degenerate_or_oob_box"] = drops.get("degenerate_or_oob_box", 0) + 1
                continue
            label = CANONICAL_ID_TO_LABEL[cat_id]
            annotations.append(
                {
                    "id": next_ann_id,
                    "image_id": image_id,
                    "category_id": cat_id,
                    "bbox": [round(float(v), 3) for v in clipped],
                    "area": round(float(clipped[2] * clipped[3]), 3),
                    "iscrowd": 0,
                    "review_status": "unreviewed_proposal",
                    "provenance": {
                        "proposal_model_id": model_id,
                        "proposal_model_revision": model_revision,
                        "proposal_method": "model_assisted",
                        "prompt": prompt,
                        "thresholds": {"score": score_threshold},
                        "source_image_sha256": str(unit["sha256"]).lower(),
                        "generated_at": generated_at,
                        "original_proposal": {
                            "bbox_xywh": [float(v) for v in det["bbox"]],
                            "score": None if score is None else float(score),
                            "prompt": prompt,
                        },
                        "human_edit_state": "unreviewed",
                    },
                }
            )
            per_category[label] = per_category.get(label, 0) + 1
            next_ann_id += 1

    doc = {
        "info": {
            "description": "Open-vocabulary boxes as UNREVIEWED proposals — not training truth",
            "generator": "scripts/locateanything_to_proposals.py",
            "proposal_model_id": model_id,
            "proposal_model_revision": model_revision,
            "generated_at": generated_at,
            "score_threshold": score_threshold,
            "prompt_map": prompt_map,
        },
        "categories": [{"id": i, "name": n} for i, n in sorted(CANONICAL_ID_TO_LABEL.items())],
        "images": images,
        "annotations": annotations,
    }
    stats = {
        "images": len(images),
        "annotations": len(annotations),
        "per_category": per_category,
        "drops": drops,
        "categories_not_box_refinable_downstream": sorted(
            {
                CANONICAL_ID_TO_LABEL[c]
                for c in (prompt_map.values())
                if c not in SAM_BOX_REFINABLE_IDS
            }
        ),
    }
    return doc, stats


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------


def run(
    *,
    images_dir: Path,
    generator_factory: Callable[[], BoxGenerator],
    prompt_map: dict[str, int],
    model_id: str,
    model_revision: str,
    score_threshold: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = iter_image_paths(images_dir)
    if not paths:
        raise ProposalError(f"no images found under {images_dir}")
    prompts = list(prompt_map.keys())
    generator = generator_factory()
    units: list[dict[str, Any]] = []
    for path in paths:
        sha, width, height = probe_image(path)
        array = load_image_array(path)
        detections = generator.generate(array, prompts)
        units.append(
            {
                "file_name": str(path.relative_to(images_dir)).replace("\\", "/"),
                "sha256": sha,
                "width": width,
                "height": height,
                "group_id": None,
                "capture_family": None,
                "detections": detections,
            }
        )
    return build_proposal_doc(
        image_units=units,
        prompt_map=prompt_map,
        model_id=model_id,
        model_revision=model_revision,
        score_threshold=score_threshold,
    )


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def _self_test() -> int:
    """Pure-Python contract check: no model, no network, no Pillow needed."""
    prompt_map = build_prompt_map(None)

    # Two synthetic images with detections, including the traps we must survive:
    #  * an unmapped prompt ("some plant") -> counted drop, NOT coerced to rice;
    #  * a low-score detection -> dropped by threshold;
    #  * an out-of-bounds/degenerate box -> counted drop.
    units = [
        {
            "file_name": "a.png",
            "sha256": "a" * 64,
            "width": 100,
            "height": 100,
            "group_id": "g1",
            "capture_family": "fam1",
            "detections": [
                {"prompt": "cultivated rice plants", "bbox": [10, 10, 20, 20], "score": 0.9},
                {
                    "prompt": "weeds growing among the rice plants",
                    "bbox": [50, 50, 10, 10],
                    "score": 0.8,
                },
                {"prompt": "some plant", "bbox": [0, 0, 5, 5], "score": 0.99},  # unmapped
                {
                    "prompt": "cultivated rice plants",
                    "bbox": [1, 1, 1, 1],
                    "score": 0.1,
                },  # low score
                {
                    "prompt": "weeds growing among the rice plants",
                    "bbox": [200, 200, 5, 5],
                    "score": 0.9,
                },  # oob
            ],
        },
        {
            "file_name": "b.png",
            "sha256": "b" * 64,
            "width": 64,
            "height": 64,
            "group_id": None,
            "capture_family": None,
            "detections": [
                {
                    "prompt": "ambiguous vegetation that may not be rice",
                    "bbox": [5, 5, 30, 30],
                    "score": 0.7,
                },
            ],
        },
    ]
    doc, stats = build_proposal_doc(
        image_units=units,
        prompt_map=prompt_map,
        model_id="nvidia/LocateAnything-3B",
        model_revision="deadbeef",
        score_threshold=0.5,
        generated_at="2026-07-21T00:00:00Z",
    )

    assert stats["images"] == 2, stats
    # 2 kept on image a (rice + weed), 1 kept on image b (unknown). 3 total.
    assert stats["annotations"] == 3, stats
    assert stats["per_category"] == {
        "rice_protect": 1,
        "weed_target": 1,
        "unknown_vegetation": 1,
    }, stats
    # the unmapped "some plant" was dropped and counted, NOT turned into rice.
    assert any(k.startswith("unmapped_prompt=") for k in stats["drops"]), stats["drops"]
    assert stats["drops"]["below_score_threshold"] == 1, stats["drops"]
    assert stats["drops"]["degenerate_or_oob_box"] == 1, stats["drops"]
    # every annotation is an unreviewed proposal with full provenance.
    for ann in doc["annotations"]:
        assert ann["review_status"] == "unreviewed_proposal"
        prov = ann["provenance"]
        assert prov["proposal_method"] == "model_assisted"
        assert prov["human_edit_state"] == "unreviewed"
        assert prov["proposal_model_revision"] == "deadbeef"
        assert prov["prompt"] in prompt_map

    # Format compatibility with the downstream SAM step: the proposal doc must
    # index cleanly in agrinav/data/sam_box_to_mask.py. rice+weed refine; the
    # unknown_vegetation box is a *counted* drop there (category not in the
    # closed SAM map) — proving no silent normalisation to rice.
    from agrinav.data.sam_box_to_mask import index_proposals

    sam_units, sam_drops = index_proposals(doc)
    refinable = sum(len(u["boxes"]) for u in sam_units)
    assert refinable == 2, (refinable, sam_drops)  # rice + weed only
    assert sam_drops.get("category_id=3") == 1, sam_drops  # unknown_vegetation dropped, counted

    print("locateanything_to_proposals self-test: OK")
    print(f"  images={stats['images']} annotations={stats['annotations']}")
    print(f"  per_category={stats['per_category']}")
    print(f"  drops={stats['drops']}")
    print(f"  downstream SAM refinable boxes={refinable}, sam_drops={sam_drops}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Open-vocabulary boxes -> UNREVIEWED COCO proposal layer"
    )
    ap.add_argument("--self-test", action="store_true", help="run the contract check and exit")
    ap.add_argument("--images-dir", type=Path, help="folder of images to propose on")
    ap.add_argument("--out-json", type=Path, help="output COCO proposal path")
    ap.add_argument("--model-id", default="nvidia/LocateAnything-3B")
    ap.add_argument(
        "--model-revision",
        default="PIN_BEFORE_RUN",
        help="pinned immutable commit sha (^[0-9a-f]{7,40}$); 'PIN_BEFORE_RUN' is refused",
    )
    ap.add_argument("--score-threshold", type=float, default=0.3)
    ap.add_argument(
        "--prompt-map",
        default=None,
        help="override prompt->category as 'prompt=cat_id;prompt=cat_id' "
        "(ids per data/ontology.v1.json). Default mirrors pilot_v1.json.",
    )
    ap.add_argument(
        "--generator-factory",
        default=None,
        help="'module:attr' returning a BoxGenerator. Required for a real run.",
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.images_dir is None or args.out_json is None:
        ap.error("--images-dir and --out-json are required (or use --self-test)")

    try:
        revision = validate_model_revision(args.model_revision)
        prompt_map = build_prompt_map(args.prompt_map)
        factory = (
            load_generator_factory(args.generator_factory)
            if args.generator_factory
            else default_generator_factory(args.model_id, revision)
        )
        doc, stats = run(
            images_dir=args.images_dir,
            generator_factory=factory,
            prompt_map=prompt_map,
            model_id=args.model_id,
            model_revision=revision,
            score_threshold=args.score_threshold,
        )
    except ProposalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(doc), encoding="utf-8")
    print(f"Wrote {args.out_json} (UNREVIEWED proposals — not training truth)")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    if stats["categories_not_box_refinable_downstream"]:
        print(
            "  note: categories "
            f"{stats['categories_not_box_refinable_downstream']} are emitted as "
            "proposals but scripts/sam_box_to_mask.py refines only rice/weed "
            "boxes; route the rest through a semantic-mask / SAM3-text path."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
