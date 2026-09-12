# Project case study

## From research prototype to measurable ML system

AgriNav began as an academic rice detector. The harder engineering problem was not adding another model layer; it was determining which results were trustworthy and building a pipeline that could expose silent failures.

I focused the project on four questions:

1. Can the dataset be rebuilt reproducibly without split or geometry mistakes?
2. Can training failures be observed before they consume another full GPU run?
3. Does evaluation measure decoded detections rather than a convenient proxy such as training loss?
4. Can every claim be separated from safety, licensing, and domain assumptions it does not support?

## 1. Dataset reconstruction and governance

The received detector data mixed native folders, a separate grouped-split manifest, EXIF-rotated images, and unreviewed SAM polygons. An earlier export had mis-assigned 940 files and included 231 intended test images in the training archive.

I built a deterministic source-to-artifact pipeline that:

- assigns images from the authoritative manifest rather than folder names;
- applies and strips EXIF orientation before checking annotations;
- clips only ≤1-pixel excursions and rejects larger invalid boxes;
- records per-image and emitted-file SHA-256 hashes;
- rejects cross-split duplicates and stray/unclaimed files;
- preserves model-generated polygons as proposals rather than human truth; and
- packages train/validation data without silently including the test split.

The rebuilt dataset contains 2,579 images and 81,201 valid boxes: 70,750 `rice_protect` and 10,451 `weed_target`. The process normalized 214 images, clipped 115 boxes, rejected 3 invalid annotations, and found zero duplicate image hashes.

## 2. Correct evaluation before better scores

The earlier detector could lower its loss without producing useful decoded detections. I implemented one canonical evaluation path shared by validation and offline scoring:

- class-aware anchor/class expansion;
- per-class NMS or Soft-NMS;
- exact inverse letterbox mapping and clipping;
- explicit dataset-category mapping;
- COCO AP/AR with standard `maxDets=100`; and
- checkpoint selection on validation AP instead of loss.

The evaluator is tested end-to-end: an exact-ground-truth stub scores AP 1.0, while shifted boxes or a swapped class map reduce the score.

## 3. Diagnosing the optimizer bottleneck

A corrected two-epoch pilot recorded gradient-norm quantiles, clipped-step fraction, positive and negative classification losses, BatchNorm state, and train/eval confidence parity.

The key finding was stark: `grad_clip=0.5` fired on 100% of steps in both the RiceSEG and ImageNet arms. Median pre-clip norms were 5.377 and 8.207; the configured clip was shrinking ordinary steps by roughly 10–16× and the tail by as much as 80×.

Under the same eight-image, 60-epoch overfit setting, increasing the clipping ceiling changed AP50 from 0.0064 to 0.3331—a 52× improvement. With the correctly sized 16-image/150-epoch gate, the pipeline reached:

| Metric | Result |
|---|---:|
| COCO AP | 0.5224 |
| AP50 | 0.8750 |
| AR@100 | 0.6315 |
| Train/eval confidence ratio | 1.01 |
| Loss | 4.5681 → 0.2309 |
| Clipped steps | 0.0% |

This was a better debugging result than a generic hyperparameter sweep because the instrumentation showed the causal mechanism.

## 4. Measuring transfer-learning directionally

The same pilot showed the RiceSEG warm start was doing useful early work:

- positive classification loss fell 50.8% in the RiceSEG arm;
- it fell 26.0% in the ImageNet control; and
- the RiceSEG gradient distribution was lower and tighter.

That is directional evidence from two epochs and one seed—not a final model claim. The portfolio keeps this distinction explicit.

## Engineering outcomes

- Installable `src/` package and unified CLI.
- Deterministic builders and fail-closed preflight validation.
- Atomic checkpoints, status files, JSONL metrics, and resume support.
- One canonical post-processing/evaluation implementation.
- Controlled baseline harness for Faster R-CNN, RetinaNet, and FCOS.
- CPU CI across Python 3.11/3.12 plus linting, packaging, and coverage reporting.
- Recorded suite of 308 passing tests plus 16 subtests.

## What remains

1. Run the corrected 18-epoch detector experiment.
2. Run at least one maintained-model baseline under the same protocol.
3. Repeat the chosen conditions across multiple seeds.
4. Add independent farm/season/camera data and explicit OOD slices.
5. Resolve dataset and project licensing before granting reuse rights.

## Interview discussion prompts

- How I detected a dataset archive that looked valid but violated its split manifest.
- Why decoded AP revealed a failure that decreasing loss concealed.
- How to use instrumentation to distinguish BatchNorm symptoms from optimizer causes.
- Why model proposals, human labels, and treatment decisions require different schemas.
- How I decide when an experiment is directional evidence versus a publishable claim.

