# Baselines — what a WeedDet AP gets measured against

An AP is not a result. `mAP@[.50:.95] = 0.31` is neither good nor bad in
isolation: it depends on the dataset's difficulty, the resolution, the class
balance, the evaluator's `maxDets`, and how the boxes were suppressed. The only
way to turn it into a claim is to run a maintained reference detector through the
*same* pipeline and report both numbers.

`docs/GATE_STATUS.md` blocks any headline accuracy claim on exactly this. This
page is how the block gets lifted.

## The harness

```bash
agrinav baseline-detector --help
```

`src/agrinav/training/baseline_det_control.py`, configured by
`configs/training/baseline_det_control.yaml`. Three reference architectures:

| `--arch` | Family | Why it is here |
|---|---|---|
| `fasterrcnn_resnet50_fpn_v2` | two-stage | the conservative strong reference; usually the hardest to beat on small objects |
| `retinanet_resnet50_fpn_v2` | one-stage dense, anchor-based | WeedDet's own family — the closest thing to an apples-to-apples control |
| `fcos_resnet50_fpn` | one-stage dense, anchor-free | tests whether WeedDet's anchor design is carrying anything |

## What makes the comparison valid

Comparability is enforced in code, not by convention. Four things are held
identical and one cannot be, and the one that cannot is recorded in every report.

**1. Same pixels.** The baseline trains on `_CocoSplitDataset` — the exact class
the WeedDet trainer uses. Same letterbox, same per-axis scales, same
label-aligned augmentation, same ImageNet normalisation, same class map. Not a
reimplementation of them.

**2. Same input tensor.** torchvision detectors resize and normalise inside the
model by default. Both are disabled (`image_mean=[0,0,0]`, `image_std=[1,1,1]`,
`min_size == max_size == img_size`), so the reference receives the tensor WeedDet
receives. `img_size` must be a multiple of 32 or the run is rejected — torchvision
pads the batch up to a multiple of 32, which would silently hand the reference a
larger canvas.

**3. Same scoring path.** Predictions go through the same `invert_letterbox` and
`to_coco_detections` as the WeedDet arm, and the same `pycocotools` call at the
same `maxDets=100`. A stub predicting exactly the ground truth scores AP 1.0
through it; shifting the boxes 25 px, or dropping the label shift, moves that
number. Both are regression tests.

**4. Same budget.** `img_size`, `num_epochs`, `seed`, `class_names` and
`val_ap_interval` are asserted equal between the two configs by a test. A
baseline trained on a different budget is a different experiment, not a control.

**5. The one difference that remains.** torchvision applies **hard NMS inside the
model**; the WeedDet arm defaults to **Soft-NMS**. Score threshold, NMS IoU and
detections-per-image are matched, but the suppression algorithm is not, and
cannot be without reimplementing torchvision's heads. Every baseline report
carries a `protocol.suppression` field naming this. **For a strict head-to-head,
score the WeedDet arm with `--hard-nms`.**

Two further honest differences, both recorded in `run.json`:

- **Optimiser recipe.** The baseline uses torchvision's reference SGD
  (`base_lr 0.005`, warmup by iteration), not WeedDet's `0.001`. Tuning a
  baseline *down* to the candidate's LR is the one direction a baseline must
  never be wrong in.
- **Batch size.** 4 rather than 8 — a two-stage detector does not fit at 8 on the
  same card. Throughput, not recipe.

## Running one

Order matters: train the baseline on `train`, select on `valid` AP, and leave
`test` alone until every arm is frozen.

```bash
agrinav baseline-detector \
  --arch fasterrcnn_resnet50_fpn_v2 \
  --config configs/training/baseline_det_control.yaml \
  --ann-file        <data>/annotations/instances_train.coco.json \
  --images-root     <data>/images/train \
  --val-ann-file    <data>/annotations/instances_valid.coco.json \
  --val-images-root <data>/images/valid \
  --out-dir <runs>/baseline_frcnn
```

Checkpoint selection is on validation AP, for the same reason the WeedDet trainer
selects on it: a detector can lower its loss while its detections get worse. A run
given no validation split writes a `warning` into `run.json` saying it is a
plumbing check and not a baseline.

Plumbing check, no dataset and no GPU needed:

```bash
agrinav baseline-detector --self-test
```

## Reading the result

`run.json` carries the full config, per-epoch losses, `best_val_ap` and
`best_epoch`. To score a frozen baseline checkpoint on a split, the protocol
block in its report must match the WeedDet report's field for field. If
`img_size`, `score_threshold`, `nms_iou` or `max_detections` differ, the two APs
are different quantities and must not be put in the same table.

`max_detections` other than 100 is not a COCO-comparable AP at all — `pycocotools`
computes the primary AP at `maxDets=100` only, and the report returns the `-1.0`
sentinel with a warning rather than a plausible wrong number.

## What is still missing after the baselines run

A baseline establishes *difficulty*, not *readiness*. Even with all three arms
reported:

- **No external validity.** Every image here comes from one capture population.
  The manifest records no farm, season, device, camera height or illumination, so
  nothing supports a claim beyond it. A different-field, different-season set is
  separate work.
- **Resolution is unjustified.** 56% of train boxes are COCO-small at 512 px and
  32.6% have a minimum side under 16 px. A resolution or tiled-inference study
  belongs before 512 is accepted as the operating point.
- **Single seed.** One run per arm ranks arms; it does not measure the gap. Repeat
  the close comparisons across seeds before reporting a difference as real.
