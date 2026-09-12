"""Inference-side building blocks.

Currently this package holds exactly one thing: the canonical detection
postprocessor (:mod:`agrinav.inference.postprocess`), shared by training-time
validation, offline evaluation, and any future runtime. There is deliberately no
runtime here — see ``README.md`` for the conditions a replacement must meet
before one is added.
"""

from agrinav.inference.postprocess import (
    class_aware_suppression,
    decode_batch,
    decode_deltas,
    expand_class_candidates,
    invert_letterbox,
    to_coco_detections,
)

__all__ = [
    "class_aware_suppression",
    "decode_batch",
    "decode_deltas",
    "expand_class_candidates",
    "invert_letterbox",
    "to_coco_detections",
]
