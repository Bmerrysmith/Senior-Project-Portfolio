"""AgriNav detection models.

``weeddet_v6b`` is the current custom detector. It still has **open Gate-4
correctness items** (Python-loop NMS, anchor volume, a single canonical
postprocessing path, regression balance, and the standard COCO evaluator); see
``docs/audits/2026-07-20/PHASE2_DETECTOR_FIXLOG_2026-07-21.md``. Its historical
T7d result is *not* a valid performance baseline, and the detector must not be
trained for field use until those items are closed.

The module is deliberately held byte-stable (excluded from the auto-formatters
in ``pyproject.toml``) because the July-20 audit references its exact line
numbers; it is reformatted only when that Gate-4 rewrite lands.
"""
