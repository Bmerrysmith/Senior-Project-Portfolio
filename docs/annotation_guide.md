# AgriNav Perception Annotation Guide v1

**Status:** research pilot draft  
**Date:** 2026-07-20  
**Scope:** image-space classification and localization only; this guide does not authorize treatment or robot control.

This guide is the human source of truth for the annotation bakeoff. The machine-readable class map is [`data/ontology.v1.json`](../data/ontology.v1.json). Model output is always a proposal. Only a human-accepted or adjudicated annotation is ground truth.

## 1. Decision rule

Annotate what is visibly supported:

- cultivated rice becomes `rice_protect`;
- an affirmatively identified biological weed becomes `weed_target`;
- ambiguous plant material becomes `unknown_vegetation`;
- duckweed or other aquatic vegetation remains `non_target_aquatic` until an agronomic policy explicitly changes it;
- unusable or protected ground regions may become `ground_exclusion`.

Never use “not rice” as the definition of a weed. Never turn a model's empty output into `verified_empty`. `treatment_eligible` is a nullable, separately reviewed attribute; it is not inferred from a class label.

## 2. Canonical labels

| Label | Canonical geometry | Meaning | Derived geometry |
|---|---|---|---|
| `rice_protect` | instance or semantic mask/polygon | cultivated rice that must be protected | tight box around visible mask |
| `weed_target` | instance mask/polygon | affirmative weed evidence | tight instance box |
| `unknown_vegetation` | instance or semantic mask/polygon | plant identity is unresolved | tight box for hard-negative analysis |
| `non_target_aquatic` | semantic mask/polygon | duckweed/aquatic vegetation with no approved target policy | optional box |
| `ground_exclusion` | semantic mask/polygon | water/reflection, equipment, marker, or region that must not be treated | none required |

Species is an attribute, not a replacement for the decision label. Additional protected crop species require their own data, guide examples, and locked evaluation before entering the ontology.

## 3. Boundary rules

### 3.1 Thin rice leaves and weed blades

- Trace visible leaf/blade pixels at the native annotation resolution.
- Keep real holes between leaves as background; do not fill a whole convex hull.
- Include thin tips when they remain visually connected and at least one pixel wide at native resolution.
- Exclude uncertain motion blur or reflection; mark the object `uncertain` or route the region to `unknown_vegetation`.
- Do not use a broad box-shaped brush around narrow leaves.

### 3.2 Occlusion and touching plants

- Annotate only the visible area; do not hallucinate hidden geometry.
- Keep distinct instances separate when stems, growth centers, or continuous boundaries support separation.
- When rice and weed touch, draw separate masks up to the visible boundary. Do not assign shared pixels to both masks.
- If the boundary cannot be resolved, label the ambiguous connected portion `unknown_vegetation` and leave the clearly resolved portions with their classes.
- Record `occlusion=partial` or `occlusion=severe` for instances whose visible geometry is materially reduced.

### 3.3 Borders and truncation

- Annotate a partial plant at an image edge when enough visible material supports its identity.
- Set `truncated=true`; do not extrapolate outside the image.
- For a RiceSEG tile, retain its `source_photo_id` so all sibling tiles stay in one split.

### 3.4 Minimum visible size

- Pilot rule: annotate any resolved target/protect plant region with at least 16 visible pixels or a minimum 4x4-pixel tight box.
- Smaller resolved regions may be marked with a point/flag for a dedicated tiny-object audit, but they must not silently disappear.
- If identity is unresolved at that scale, use `unknown_vegetation`, not a guessed class.
- Report performance separately for COCO-small objects and for the pilot's sub-16-pixel audit set.

## 4. Difficult biological cases

### Senescent rice and panicles

- Senescent leaves and rice panicles remain `rice_protect` when visibly attached to or identifiable as cultivated rice.
- Detached residue is non-vegetation or `ground_exclusion`, not protected rice.
- If a brown/yellow plant cannot be distinguished from residue or a weed, use `unknown_vegetation`.

### Grasses and rice-like weeds

- Morphological similarity alone is insufficient for `weed_target`.
- Use row context, stem/growth center, leaf arrangement, and any available agronomic reference.
- Weedy rice is a special hard class. Store `species=weedy_rice` (or the approved local term) and default it to `unknown_vegetation` until a project-specific agronomic rule is approved.

### Duckweed and submerged plants

- Label visible duckweed/aquatic cover as `non_target_aquatic`.
- Do not merge duckweed with ground/background and do not call it a target solely because RiceSEG uses a weed-adjacent category.
- Partially submerged uncertain vegetation becomes `unknown_vegetation`.

### Reflections, glare, and shadows

- Reflected vegetation is not a second plant instance.
- Water reflection, specular glare, deep shadow, mud, and open water are background or `ground_exclusion` when they obscure or invalidate target geometry.
- If a reflection makes an actual plant boundary uncertain, annotate only certain pixels and flag the object/region for review.

### Volunteer rice and non-rice crops

- Do not map a generic external crop label to `rice_protect`.
- Volunteer or weedy rice remains a dedicated biological attribute and an unresolved decision role until agronomic policy is recorded.
- A non-rice crop in an auxiliary dataset retains its source ontology and is ignored or adapted through a dataset-specific head; it is never silently relabeled as rice.

## 5. Image-level states

### Verified empty

Set `verified_empty=true` only when a human has inspected the full native-resolution image and found no `weed_target` objects. The image may contain rice, unknown vegetation, aquatic vegetation, or exclusion regions. Required checks:

1. zoom the full image;
2. inspect borders, shadows, water, and small-object regions;
3. record annotator ID, timestamp, and guide version;
4. obtain independent review for every locked test/challenge negative.

`verified_empty=false` means at least one accepted `weed_target` exists. `verified_empty=null` means the state has not been verified. Model silence never changes `null` to `true`.

### Unusable image

Set `unusable=true` when blur, corruption, obstruction, exposure, or missing pixels prevent reliable full-frame review. Do not use unusable images as verified negatives. Preserve them as an OOD/failure slice when appropriate.

## 6. Required object and image attributes

For every object record:

- biological class and canonical label;
- source object ID;
- species or `null`;
- growth stage or `null`;
- occlusion (`none`, `partial`, `severe`, `unknown`);
- truncation flag;
- annotation confidence (`certain`, `probable`, `uncertain`);
- `treatment_eligible` as separately reviewed `true`, `false`, or `null`;
- proposal provenance when model-assisted.

For every image record:

- SHA-256, source dataset/version, and exact source path;
- site/field/session/pass/frame/source-photo group fields, using explicit `null` for unknown values;
- dimensions and capture metadata where available;
- `verified_empty`, `unusable`, annotator, reviewer, review state, annotation version, and guide version.

## 7. Model-assisted proposal provenance

Keep the original proposal unchanged in a proposal layer. The final human layer must record:

- proposal method, model ID, immutable revision/hash, prompt, thresholds, and generation time;
- source image SHA-256;
- original boxes/points/masks/scores exactly as emitted;
- human action per object (`accepted`, `edited`, `deleted`, `added`, `reclassified`, `split`, `merged`);
- annotator/reviewer IDs and timestamps;
- final review state.

LocateAnything produces boxes/points, not canonical masks. Refine its boxes with SAM2.1/SAM3 and then review the mask. Grounding DINO proposals follow the same rule. Never normalize every generic `plant` detection to rice, as the historical `data/auto_annotate.py` prototype does.

## 8. Pilot and review workflow

1. Select 200 source-group-diverse images using [`configs/annotation/pilot_v1.json`](../configs/annotation/pilot_v1.json).
2. Choose 40 images as a gold subset before running proposal models. Two annotators label these independently without seeing model output.
3. Adjudicate the gold subset and revise this guide once before the proposal bakeoff.
4. Run three proposal conditions on the same remaining images:
   - LocateAnything boxes -> SAM2.1 masks;
   - Grounding DINO boxes -> SAM2.1 masks;
   - SAM3 text-to-mask.
5. Randomize proposal presentation so the annotator does not know the method when practical.
6. Time active correction work per image and object. Record additions as carefully as edits; missed weeds are more important than easy accepted masks.
7. Double-label 10-20% of routine data, biased toward tiny weeds, overlap, negatives, glare/reflection, senescence, and uncertainty.
8. Independently review and adjudicate every locked test/challenge image used for safety-relevant claims.

Recommended tools:

- [CVAT](https://docs.cvat.ai/) for the canonical mask/polygon tasks, consensus/review, and COCO instance export;
- [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) for the fastest Windows model-proposal pilot, including LocateAnything/SAM integrations;
- [FiftyOne](https://docs.voxel51.com/) for group-aware selection, exact/near duplicates, uniqueness, error slices, and annotation round trips.

### Local intake commands

Build the deterministic pilot and its empty, manual-first annotation intake without extracting either raw archive:

```powershell
python -B scripts\build_annotation_pilot.py `
  --config configs\annotation\pilot_v1.json `
  --riceseg-zip <path-to-RiceSEG.zip> `
  --coco-zip <path-to-rice_detection_for_export.zip> `
  --output-manifest artifacts\annotation_pilot_v1\manifest.json `
  --output-annotation-jsonl artifacts\annotation_pilot_v1\annotation_intake.jsonl
```

The builder hashes every selected image, freezes the gold-subset membership, leaves capture fields explicitly `null` when unknown, and leaves every annotation/verified-empty decision unreviewed. Existing RiceSEG masks and COCO boxes remain proposal evidence in the selection manifest; they are not copied into the manual-first JSONL as accepted truth.

After human/export conversion, validate an annotation package before it can enter a split:

```powershell
python -B scripts\validate_annotation_package.py artifacts\annotation_v1\annotations.jsonl `
  --check-split-overlap `
  --manifest data\manifests\split-v1.json
```

### End-to-end automated pipeline

For the scripted open-vocabulary → SAM → review → **YOLOv8/v11 export** loop
(box proposals via [`src/agrinav/data/locateanything_to_proposals.py`](../src/agrinav/data/locateanything_to_proposals.py)
and dataset export via [`src/agrinav/data/export_yolo_dataset.py`](../src/agrinav/data/export_yolo_dataset.py)),
see the runbook in [`automated_annotation_pipeline.md`](automated_annotation_pipeline.md).
Both ends emit or consume *proposals*; only the human review stage in this
section mints truth, and the exporter is truth-only by default.

## 9. Quality metrics and provisional gates

Report full distributions by class, object size, source group, hard condition, annotator, and proposal method.

| Measure | Pilot gate |
|---|---:|
| class/treatment-status agreement after guide stabilization | >= 98% |
| median matched-instance box IoU | >= 0.85 |
| median mask IoU | >= 0.80 |
| invalid, duplicate, zero-area, or out-of-bounds rate | < 0.1% |
| locked test/challenge verified-empty independent review | 100% |
| locked high-risk disagreement adjudication | 100% |

For proposal-method selection, require weed recall >= 0.95 at IoU 0.50 on the gold pilot, report recall at IoU 0.75, and then choose the passing method with the lowest median human correction time. If no method passes, use interactive SAM2.1 mask editing without accepting batch pseudo-labels.

## 10. Release checklist

An annotation version can be released only when:

- every image and annotation resolves to a hashed source;
- every derivative inherits its source group;
- category IDs and geometry validate;
- `verified_empty` never coexists with a positive `weed_target`;
- masks and boxes are in bounds and non-degenerate;
- no duplicate annotations remain;
- proposal and human layers are distinguishable;
- required independent reviews and adjudications are complete;
- no split contains sibling tiles/frames/sessions from another split;
- the release records ontology, guide, source data, annotation, and split versions.
