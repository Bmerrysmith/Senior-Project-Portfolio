# Project Source

Curated source from my senior project. This is an excerpt, not a full mirror.
Datasets, images, model weights, checkpoints, executed notebooks, and run
artifacts are left out to keep the repo light.

For full history and the complete tree, see the original repo:

- **AgriNav** — https://github.com/Bmerrysmith/Autonomous-tractor-system (snapshot of commit `ed93be5`)

## agrinav/

Rice/weed perception for an autonomous paddy tractor. Start with
[`agrinav/README.md`](agrinav/README.md) for the technical deep dive. What's here:

- `src/agrinav/models/weeddet_v6b.py` — the WeedDet detector: Det-ResNet-50, eFPN, ERetina head, anchors, ATSS assignment, losses
- `src/agrinav/data/build_rice_phase2.py` — the fail-closed dataset rebuild (manifest-driven splits, EXIF fix, SHA-256 preflight)
- `src/agrinav/data/anchor_audit.py` — measures how well the anchor set covers the ground-truth boxes
- `src/agrinav/inference/postprocess.py` — the one canonical class-aware decode, per-class NMS, and inverse letterbox
- `src/agrinav/evaluation/` — model-to-COCO conversion and pycocotools AP/AR
- `src/agrinav/training/` — detector training with instrumentation, RiceSEG pretraining, pilot report, and the segmentation/detector baseline controls
- `configs/training/` — versioned, path-free experiment configs (`detector_rice_phase2.yaml` documents the gradient-clip decision inline)
- `tests/` — CPU pytest suite for the included modules, no data or GPU needed
- `docs/` — dataset card, baseline protocol, the post-processor ADR, a training quickstart, and machine-readable results
- `reports/metrics/` — anchor-coverage audits for the train and validation splits

Left out: the annotation-proposal tooling (SAM box-to-mask, LocateAnything
proposals, triage, YOLO export, annotation schema validation) and its tests,
earlier split builders superseded by the phase-2 rebuild, the Colab notebooks,
and the research audit logs. All of it is in the source repo.
