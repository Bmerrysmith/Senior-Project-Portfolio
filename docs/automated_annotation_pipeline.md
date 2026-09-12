# Automated Annotation Pipeline (open-vocab boxes → SAM masks → YOLOv8/v11)

**Status:** research pilot tooling
**Scope:** image-space *proposal* generation and dataset export only. This
pipeline produces **proposals**, not ground truth. Only a human-accepted or
adjudicated annotation is truth ([`annotation_guide.md`](annotation_guide.md) §7–8,
[`../data/ontology.v1.json`](../data/ontology.v1.json)). Nothing here authorizes
treatment or robot control.

This is the concrete, script-by-script version of the common
"VLM → SAM → YOLO" auto-labelling loop, wired to this project's ontology and its
proposals-never-truth governance. The middle (SAM box→mask) and the review/
validation stages already existed; the two ends — an open-vocabulary box
generator and a YOLO exporter — are added by
[`../src/agrinav/data/locateanything_to_proposals.py`](../src/agrinav/data/locateanything_to_proposals.py)
and [`../src/agrinav/data/export_yolo_dataset.py`](../src/agrinav/data/export_yolo_dataset.py).

## The flow

| Stage | Script | Output | Truth? |
|---|---|---|---|
| 1. Open-vocab boxes | `locateanything_to_proposals.py` | COCO proposals | ❌ unreviewed |
| 2. Box → mask | `sam_box_to_mask.py` | raw SAM candidate JSONL (RLE) | ❌ unreviewed |
| 3. Route to review | `triage_proposals.py` | review buckets | ❌ unreviewed |
| 4. **Human review / adjudication** | CVAT / X-AnyLabeling + `validate_annotation_package.py` | accepted records JSONL | ✅ **the only truth step** |
| 5. Export | `export_yolo_dataset.py` | Ultralytics `images/ labels/ data.yaml` | ✅ truth-only by default |

> Stage 4 is not optional and cannot be automated away. The forbidden inference
> `proposal => accepted ground truth` is the reason the proposal layer and the
> truth layer are kept physically separate.

## Safety invariants baked into the new scripts

- **No default label.** Stage 1 maps each *prompt* to one ontology category
  through a closed dict; an unmapped or ambiguous prompt is a *counted drop* or
  maps to `unknown_vegetation` — never coerced to `rice_protect`/`weed_target`.
  This is the exact anti-pattern quarantined in
  `_archive/unsafe_inference/auto_annotate.py`.
- **Pinned models.** Stage 1 refuses `--model-revision PIN_BEFORE_RUN` and
  requires an immutable commit sha, matching `sam_box_to_mask.py`.
- **Truth-only export.** Stage 5 exports only `accepted`/`adjudicated`,
  non-`unusable` records and drops per-object `human_edit_action == "deleted"`.
  `--include-unreviewed` exists for a bootstrapping loop but stamps
  `UNREVIEWED_DO_NOT_TRAIN.txt` and records the weakened gate.
- **Sealed split.** Stage 5 places each record by its immutable `source.split`;
  `unassigned` is never dumped into `train`, so the sealed test set stays sealed.
- **No fabricated geometry.** In `--task segment`, a box-only annotation is a
  counted skip, not an invented rectangle-mask.

## Runbook

Contract checks (no GPU, no network, no model downloads):

```bash
agrinav data-locateanything --self-test
agrinav data-export-yolo --self-test
```

### 1. Generate box proposals on unlabelled images (GPU / WSL / Colab)

Heavy open-vocab inference needs a GPU environment and an accepted upstream
model licence; LocateAnything-3B weights are non-commercial research assets.
Wire a backend via `--generator-factory module:attr` returning a `BoxGenerator`
(LocateAnything, Grounding DINO, …), then:

```bash
agrinav data-locateanything \
  --images-dir data/rice_training_curated/aerial \
  --model-id nvidia/LocateAnything-3B \
  --model-revision <pinned-commit-sha> \
  --generator-factory yourpkg.locate:make_generator \
  --out-json artifacts/annotation/locateanything_proposals_unreviewed.coco.json
```

Prompt→category defaults mirror the `locateanything_sam21` method in
[`../configs/annotation/pilot_v1.json`](../configs/annotation/pilot_v1.json);
override with `--prompt-map "cultivated rice plants=1;weeds among rice=2"`.

### 2. Refine boxes to masks with SAM2.1

The proposal JSON above is drop-in input to the existing SAM step (only
`rice_protect`/`weed_target` boxes are box-refinable; other categories are a
counted drop there and should take a semantic-mask / SAM3-text path):

```bash
agrinav data-sam-mask \
  --coco-zip <images.zip> \
  --proposals-json artifacts/annotation/locateanything_proposals_unreviewed.coco.json \
  --model-revision <pinned-sam-sha> \
  --out-shard artifacts/annotation/sam_candidates_%03d.jsonl
```

### 3–4. Triage, review, validate

Route with `agrinav data-triage`, review in CVAT/X-AnyLabeling, then
gate the resulting package before it can enter a split:

```bash
agrinav data-validate artifacts/annotation/reviewed/annotations.jsonl \
  --check-split-overlap --manifest data/manifests/detector_split_v1.json
```

### 5. Export a YOLOv8/v11 dataset

Truth-only by default. `--task segment` uses polygons (canonical geometry);
`--task detect` uses boxes for the YOLOv8s baseline the roadmap calls for.

```bash
agrinav data-export-yolo \
  --packages artifacts/annotation/reviewed/*.jsonl \
  --images-root ~/agrinav_data/derived/images \
  --out-root artifacts/yolo/weeddet_v1 \
  --task segment --classes rice_protect,weed_target
```

Output is a standard Ultralytics tree (`images/{train,val,test}`,
`labels/{...}/*.txt`, `data.yaml`) plus `export_report.json` with per-split,
per-class, and drop counts. Train with any Ultralytics YOLOv8/v11 model, e.g.
`yolo segment train data=artifacts/yolo/weeddet_v1/data.yaml model=yolo11n-seg.pt`.
```
