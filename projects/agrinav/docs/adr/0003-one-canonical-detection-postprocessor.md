# ADR 0003: One canonical detection postprocessor, and AP-based checkpoint selection

## Status

Accepted — 2026-07-29

## Context

Two independent audits on 2026-07-29 landed on the same structural problem from
different directions, and verification confirmed both.

**The decode was wrong in two ways at once.** `WeedDet._decode` reduced each
anchor to its single highest-scoring class (`sigmoid().max(dim=1)`) and then ran
one Soft-NMS/NMS pass across every surviving detection regardless of label. So an
anchor that fired on rice *and* weed contributed only the stronger hypothesis,
and a rice box could delete an overlapping weed box. In a rice paddy — where the
weeds are physically among the rice — that is not an edge case, and the weed
class is the minority at 6.8:1.

**Nothing scored the detector.** The repository had an honest `pycocotools`
primitive (`agrinav.evaluation.metrics`) with good unit tests, and it had a
detector. It had no adapter between them. The consequence was that checkpoint
selection ran on training loss, later improved to validation loss — neither of
which is detection quality. Two completed A100 runs selected `best` on training
loss whose last-five-epoch spread was about the size of the augmentation noise on
the same quantity; that selection was ranking noise.

Three postprocessing regimes were implied across the code, the notebook, and the
documentation, with nothing making one of them authoritative.

## Decision

**One postprocessor, in `agrinav.inference.postprocess`, used by everything.**

- Every `(anchor, class)` pair above threshold becomes an independent candidate.
- Suppression happens **within** a class and never across classes, via
  `torchvision.ops.batched_nms` (which explicitly does not suppress between
  categories) or per-class Soft-NMS. The torch-only fallback reproduces
  torchvision's coordinate-offset trick.
- Top-k before suppression is **per class**, not global. A shared cap is a cap the
  majority class wins: with a 6.8:1 ratio, above-threshold rice candidates can
  evict above-threshold weed candidates before the metric ever sees them.
- `max_detections` defaults to 100, matching the COCO `maxDets` the metric
  defaults to, so what is produced and what is scored cannot silently diverge.
- The inverse letterbox lives here too and **clips to the original image**,
  dropping boxes that existed only in the padding.

`WeedDet._decode` delegates to it. `nms`/`soft_nms`/`box_iou` moved here and are
re-exported from the monolith for compatibility, so there is one implementation
rather than two that can drift.

**`agrinav.evaluation.runner` is the model-to-COCO adapter**, exposed as
`agrinav evaluate-detector`. It records the full protocol — image size, score
threshold, NMS IoU, max detections, Soft-NMS on/off, top-k — beside the metrics,
so two runs can be compared, or shown to be incomparable.

**Checkpoint selection uses validation AP** when `val_ap_interval > 0`: the EMA
weights (the ones actually saved) are decoded over the validation split and
scored, and `best` is the maximum AP rather than the minimum loss. The comparison
direction flips with the metric; selecting AP with a `<` comparison would keep
the worst epoch, so that direction is a tested invariant.

## Alternatives considered

**Keep class-agnostic NMS and tune the IoU threshold.** Rejected: no threshold
makes a rice box the correct suppressor of a weed box. This is a correctness bug,
not a tuning preference.

**Global top-k, as torchvision's RetinaNet uses (per level).** Rejected for this
dataset specifically. Per-level top-k is a reasonable default on balanced COCO;
here the class imbalance makes per-class the cheaper and safer choice, and the
cost is negligible.

**AP every epoch.** Rejected as a default. A full decode over 518 validation
images is real time on top of each epoch. `val_ap_interval` makes the cost
explicit and tunable, and off-epochs carry the previous AP forward so `best`
never compares an AP epoch against a no-AP epoch.

**Score inside the monolith.** Rejected: the monolith is the file most in need of
being split, and the adapter is exactly the kind of logic that should be testable
without constructing a detector — as it now is, with a stub model.

## Consequences

Good:

- A rice and a weed detection on the same pixels both reach the metric, which is
  the only place that comparison belongs.
- Checkpoint selection is evidence-backed for the first time, and `metrics.jsonl`
  carries per-epoch AP, AP50, AP75, AP-small, AR100 and per-class AP.
- Offline scoring of any checkpoint is one command, with the protocol recorded.
- Training, evaluation, and any future runtime share one geometry and one
  suppression path by construction, not by convention.

Costs and risks:

- Per-epoch AP adds a decode pass over the validation split. Mitigated by the
  interval; measured per evaluation in `val/eval_seconds`.
- Soft-NMS remains a Python loop, now run once per class. Fine at current scale,
  and the first thing to vectorize if profiling says so.
- Changing the postprocessor changes what every future number means. Runs from
  before this ADR are not comparable to runs after it, independently of the data
  problems that already voided them.
- Not addressed here: `agrinav.evaluation.metrics` now fills a derivable `area`
  and `iscrowd` on ground-truth annotations that omit them, because `COCOeval`
  otherwise dies with a bare `KeyError: 'area'` deep in `evaluateImg`. Filling a
  derivable field changes no score; anything not derivable is still rejected.

## References

- `docs/audits/2026-07-29/AUDIT_VERIFICATION_2026-07-29.md` — the verification
  that established both defects, with the reproduction numbers.
- Torchvision `batched_nms`: https://docs.pytorch.org/vision/0.12/generated/torchvision.ops.batched_nms.html
- COCO detection evaluation: https://arxiv.org/abs/1405.0312
- Soft-NMS: https://arxiv.org/abs/1704.04503
- Tests: `tests/test_postprocess.py`, `tests/test_evaluation_runner.py`,
  `tests/test_training_artifacts.py::test_val_ap_interval_selects_on_ap_and_higher_is_better`
