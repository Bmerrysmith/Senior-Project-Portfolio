# Benjamin Merryman-Smith

Florida Gulf Coast University, U.A. Whitaker College of Engineering
Focus: Computer vision, deep-learning training and evaluation infrastructure, and reproducible ML experiments

[GitHub](https://github.com/Bmerrysmith)

---

## AgriNav: Rice/Weed Perception for an Autonomous Paddy Tractor

**Role:** Perception Lead, FGCU senior project (CEN 4930) | Spring 2026 to Summer 2026
**Links:** [Source repo](https://github.com/Bmerrysmith/Autonomous-tractor-system) · [Technical deep dive](../projects/agrinav/README.md)
**Note:** This covers perception only. Datasets, model weights, navigation, and spray/actuation code are not included.

### What it is

AgriNav is a senior design project building an autonomous tractor for rice paddies. I owned the perception stack: a detector that finds protected rice (`rice_protect`) and target weeds (`weed_target`) in field imagery. The detector follows the Improved RetinaNet from Peng et al. (2022) and trains on 2,579 curated images. The data is hard: 56% of boxes are COCO-small, the median image holds 31 plants, and rice outnumbers weeds 6.8 to 1.

The model started as an exploratory notebook. Most of my work went into making it trustworthy: rebuilding the dataset from source truth, measuring the model on decoded detections instead of loss, instrumenting training so failures show up before a GPU run is wasted, and running control experiments to find what is actually limiting performance.

### What I built

- **Detector (PyTorch).** Det-ResNet-50 backbone. Its stem uses two 3×3 convs plus a residual block where standard ResNet uses a 7×7 conv and max-pool, which gives P2–P4 feature maps at strides 4/8/16 for small plants. It feeds a three-level efficient FPN and an ERetina head (a 64-channel shared conv plus a 7×1 / 1×7 depthwise large-separable conv). Anchors are 12 per location, weighted toward tall shapes (aspect ratios 0.2–1.0), and an anchor audit confirmed that 99.5% of training boxes have a matching anchor at IoU ≥ 0.5. Training uses ATSS assignment and CIoU + SmoothL1 regression.
- **Dataset rebuild.** I found that the archive used for two training runs ignored its own grouped-split manifest. 940 of 2,316 files were in the wrong split, and 231 of the 261 sealed test images had been trained on. I wrote a deterministic builder that:
  - assigns every image from the manifest
  - corrects EXIF orientation on 214 images that were rotated 90° relative to their boxes
  - clips or rejects bad geometry under one documented rule
  - SHA-256 hashes every emitted file
  - re-verifies the output from disk and fails closed on any mismatch
- **One canonical post-processor.** Class-aware decoding keeps every above-threshold (anchor, class) pair. NMS and top-k run per class, so the majority rice class can no longer suppress or crowd out weeds. It also applies an exact inverse letterbox. Training validation, offline evaluation, and the baseline harness all share this code.
- **COCO evaluation and checkpoint selection.** A pycocotools adapter with `maxDets=100`. Checkpoints are selected on validation AP of the EMA weights, not on loss. An end-to-end test confirms that a perfect stub scores AP 1.0 and that shifted boxes or a swapped class map lower the score.
- **Training instrumentation.** Per-epoch gradient-norm quantiles and clipped-step fraction, positive vs. negative classification loss, and train-vs-eval BatchNorm confidence parity. Checkpoints and `status.json` are written atomically, metrics go to JSONL, and runs can resume. A pilot-report module turns a run's metrics into go/no-go decisions.
- **Control experiments.** A segmentation baseline harness (DeepLabV3, SegFormer) and a detector baseline harness (Faster R-CNN, RetinaNet, FCOS) share the same split, loss, seed, and evaluator. Only the model changes.
- **Correctness fixes.** Found and fixed silent defects in anchor assignment, augmentation, and scoring, with regression tests for each code fix:
  - ATSS top-k picked 9 anchor *shapes* at one cell instead of 9 nearby *cells*
  - an indexing collision could leave a ground-truth object with no positive anchor
  - an IoU ignore band let unsupervised anchors saturate to confidence 1.0
  - translation augmentation could separate labels from their boxes
- **Engineering.** Installable `src/` package with a single CLI, versioned path-free configs, and CPU CI on Python 3.11/3.12 with ruff, black, and mypy. The source repository records 308 tests plus 16 subtests passing.

### Selected outcomes

| Outcome | Measured result |
|---|---:|
| Rebuilt detector dataset | **2,579 images / 81,201 boxes**, 0 exact-duplicate images |
| RiceSEG backbone pretraining | mIoU **0.5827**, reproduced within **0.001** on an independent run |
| Hidden optimizer bottleneck | `grad_clip=0.5` truncated **100%** of steps (median pre-clip norm 5.4–8.2) |
| Matched overfit test after fixing the clip | AP50 **0.0064 → 0.3331** (52×) with seed, data, and epochs held fixed |
| Decoded overfit gate (16 images, 150 epochs) | AP **0.522**, AP50 **0.875**, AR@100 **0.632**, train/eval confidence ratio **1.01** |
| Architecture control, stable weed IoU | Custom backbone **0.202 ± 0.053** vs. DeepLabV3 **0.483 ± 0.006** vs. SegFormer-B2 **0.522 ± 0.002** |

### Conclusions so far

1. **The early failures were pipeline defects, not model capacity.** A leaked split, rotated labels, class-agnostic NMS, broken anchor assignment, and a gradient clip that bound every step all looked like "the model isn't learning." With those fixed, the full pipeline memorizes a small set (AP50 0.875). So the pipeline can learn, but generalization has not been measured yet.
2. **Falling loss is not evidence.** Loss fell steadily while AP50 sat at 0.006. Decoded COCO AP is the only metric I use to select or compare models now.
3. **Weed accuracy is limited by the architecture before the data.** On the same split, loss, and seed, stock segmenters reach about 2.4–2.6× the custom backbone's stable weed IoU, with a small fraction of its epoch-to-epoch variance. This reversed the project's working assumption that we needed more weed data. The next change is a standard torchvision ResNet-50 backbone that keeps the FPN/ATSS head. The caveats are one seed per model, a mismatched batch size, and a segmentation proxy for detection.
4. **Some classes are limited by data.** Senescent and duckweed plateau near 0.35 IoU under both the custom model and DeepLabV3. Loss or learning-rate tricks won't fix that; more real minority examples will.
5. **In-domain pretraining looks promising but isn't proven.** The RiceSEG warm start cut positive classification loss 50.8%, vs. 26.0% for ImageNet, with tighter gradients. That is two epochs and one seed. The 18-epoch detector A/B is the experiment that settles it.
6. **No headline detector accuracy claim yet.** That needs a full corrected run, a maintained baseline under the same protocol, multiple seeds, and independent farm/season data. Until then, a missing or uncertain detection means no treatment.

### Stack

Python, PyTorch, TorchVision, Transformers (SegFormer), OpenCV, pycocotools, NumPy, Google Colab (T4/A100 GPUs), pytest, GitHub Actions, ruff/black/mypy

### What I took away

The most valuable result was a diagnosis, not a better score. Every time the detector "improved," the first question had to be whether the measurement was honest. Most of the gains came from finding where it wasn't: a split that leaked, a metric that rewarded the wrong thing, a clip that silently set the step size. Once measurement was fixed, a single controlled experiment overturned the project's working assumption about the model's bottleneck. That kind of control run is now the first thing I reach for.
