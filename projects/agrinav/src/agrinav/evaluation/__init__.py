"""AgriNav detection evaluation.

The **metric primitive** (:mod:`agrinav.evaluation.metrics`) is deliberately
*decode-agnostic*: it consumes already-decoded predictions plus a COCO
ground-truth file and returns standard COCO AP. It imports neither ``torch`` nor
the detector, so the canonical decode/postprocess rewrite (Gate-4 item **P1-6**,
which lives in the byte-stable ``models/weeddet_v6b.py``) can change *how*
predictions are produced without changing the thing that scores them.

The model-runner adapter (dataset + checkpoint -> predictions) is intentionally
**not** here yet; it depends on the decode and is bundled with the P1-6 work so
the two land together. See ``docs/audits/2026-07-20/PHASE2_DETECTOR_FIXLOG_2026-07-21.md``.
"""
