# Portfolio results and evidence

This document distinguishes measured engineering results from future targets. The recruiter README intentionally does not claim production accuracy or field readiness.

## Metric provenance

| Claim | Included evidence |
|---|---|
| 2,579 images / 81,201 boxes and sanitation counts | `rice_phase2_dataset_card.md`; `src/agrinav/data/build_rice_phase2.py`; `tests/test_build_rice_phase2.py` |
| Phase-1 mIoU 0.5827, reproduced within 0.001 | Source-repository result log at commit `ed93be5`; compact record below |
| Gradient clipping affected 100% of pilot steps | `configs/training/detector_rice_phase2.yaml`; instrumentation and pilot-report code/tests |
| Overfit AP 0.5224 / AP50 0.8750 / AR@100 0.6315 | Source-repository gate record at commit `ed93be5`; compact record below |
| Canonical class-aware decode and COCO evaluation | `src/agrinav/inference/postprocess.py`; `src/agrinav/evaluation/runner.py`; `tests/test_postprocess.py`; `tests/test_evaluation_runner.py` |
| 308 tests + 16 subtests recorded passing | Source-repository gate record at commit `ed93be5`; the full corresponding test suite is included |

Machine-readable values are in [`evidence/results_summary.json`](evidence/results_summary.json).

## Dataset of record

| Split | Images | Boxes | rice_protect | weed_target | EXIF-normalized |
|---|---:|---:|---:|---:|---:|
| Train | 1,800 | 59,691 | 52,194 | 7,497 | 35 |
| Validation | 518 | 15,226 | 13,201 | 2,025 | 80 |
| Test | 261 | 6,284 | 5,355 | 929 | 99 |
| **Total** | **2,579** | **81,201** | **70,750** | **10,451** | **214** |

Additional build checks:

- 115 boxes clipped under a ≤1-pixel sanitation rule.
- 3 annotations rejected for larger out-of-bounds geometry.
- Zero duplicate image hashes.
- Every emitted JSON and image membership is hashed.
- A preflight command re-opens media and fails on missing, corrupt, mismatched, duplicated, or stray content.

## Phase-1 segmentation

The completed ImageNet → RiceSEG pretraining run reached validation mIoU 0.5827 at epoch 30. An independent run using the same split, seed, and recipe reproduced it within 0.001 mIoU. This closes the reproducibility gate for the backbone artifact; it is not a detector score.

## Phase-2 diagnostic pilot

| Pilot measurement | RiceSEG arm | ImageNet arm |
|---|---:|---:|
| Gradient norm p50 | 5.377 | 8.207 |
| Gradient norm p99 | 10.538 | 32.907 |
| Maximum finite norm | 13.996 | 39.667 |
| Steps clipped at 0.5 | 100% | 100% |
| Positive classification-loss reduction | 50.8% | 26.0% |
| Train/eval confidence parity | 0.84 → 0.88 | 0.71 → 0.75 |

Interpretation: the 0.5 clip, not the learning-rate schedule, was controlling ordinary steps. BatchNorm parity stayed within the preregistered [0.33, 3.00] band, so a checkpoint-breaking GroupNorm rewrite was not justified by this pilot.

## Decoded overfit gate

Matched eight-image, 60-epoch comparison:

| grad_clip | AP | AP50 | AR@100 | Clipped steps |
|---:|---:|---:|---:|---:|
| 0.5 | 0.0012 | 0.0064 | 0.0286 | 100.0% |
| 120 | 0.0628 | 0.3331 | 0.2563 | 0.0% |

That is a 52× AP50 improvement from removing the clipping bottleneck while keeping the seed, data, epoch budget, and model fixed.

The correctly sized 16-image/150-epoch gate then reached AP 0.5224, AP50 0.8750, AR@100 0.6315, confidence ratio 1.01, and loss 4.5681 → 0.2309 with no clipped steps.

## Claim boundaries

- An overfit gate proves that data, optimization, decoding, and evaluation can work together; it does not measure generalization.
- The two-epoch warm-start comparison is directional and single-seed.
- No maintained detector baseline has completed under the current protocol, so no headline architecture claim is made.
- No independent farm/season dataset has been evaluated.
- Historical contaminated detector runs and checkpoints are excluded.
- This repository includes no data, weights, treatment logic, or actuation interface.

## Snapshot verification

The public portfolio was generated from a fresh clone of `Bmerrysmith/Autonomous-tractor-system` at commit `ed93be5` on 2026-09-12. All included Python files and JSON files were parsed during packaging, local Markdown links were checked, and credential-pattern scanning was performed before publication.

The packaging environment directly ran the dependency-light data/tooling subset: **109 tests plus 16 subtests passed**. PyTorch was not installed on that machine, so the torch-backed portion was preserved but not re-run there; the 308 + 16 full-suite figure remains the source repository's recorded result.
