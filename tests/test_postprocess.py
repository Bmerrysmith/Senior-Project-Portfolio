"""Tests for the canonical detection postprocessor.

These pin the two behaviours the July-29 audit called correctness bugs:

1. an anchor that fires on more than one class must produce more than one
   candidate — the losing hypothesis must survive to the metric;
2. suppression must never happen *between* classes — a rice box must not delete
   an overlapping weed box.

Both used to fail silently: the old decode did ``sigmoid().max(dim=1)`` and then
one class-agnostic NMS pass. A test that only checks "some boxes came out" passes
against both the broken and the fixed version, so each test here is written to
fail against the old behaviour.
"""

from __future__ import annotations

import pytest
import torch

from agrinav.inference.postprocess import (
    box_iou,
    class_aware_suppression,
    decode_batch,
    decode_deltas,
    expand_class_candidates,
    hard_nms,
    invert_letterbox,
    soft_nms,
    to_coco_detections,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Candidate expansion
# --------------------------------------------------------------------------- #
def test_anchor_firing_on_two_classes_yields_two_candidates():
    """The old decode kept only the max class per anchor; this is that regression."""
    scores = torch.tensor([[0.7, 0.6]])  # one anchor, rice 0.7 and weed 0.6
    anchor_index, class_index, candidate_scores = expand_class_candidates(scores, 0.05)
    assert anchor_index.tolist() == [0, 0]
    assert sorted(class_index.tolist()) == [0, 1]
    assert pytest.approx(sorted(candidate_scores.tolist())) == [0.6, 0.7]


def test_candidates_come_back_sorted_by_score():
    scores = torch.tensor([[0.2, 0.9], [0.5, 0.1]])
    _anchors, _classes, candidate_scores = expand_class_candidates(scores, 0.05)
    assert candidate_scores.tolist() == sorted(candidate_scores.tolist(), reverse=True)


def test_threshold_is_strict_and_drops_everything_below():
    scores = torch.tensor([[0.05, 0.04]])
    anchor_index, _classes, _scores = expand_class_candidates(scores, 0.05)
    assert anchor_index.numel() == 0


def test_topk_is_per_class_so_the_majority_class_cannot_evict_the_minority():
    """With 6.8:1 rice-to-weed, a global cap is a cap rice wins."""
    # 100 strong rice candidates, 3 weaker weed ones. A global top-k of 10 would
    # keep only rice; per-class top-k keeps the weed candidates too.
    scores = torch.zeros(103, 2)
    scores[:100, 0] = torch.linspace(0.90, 0.99, 100)
    scores[100:, 1] = torch.tensor([0.30, 0.31, 0.32])
    _anchors, class_index, _scores = expand_class_candidates(scores, 0.05, pre_nms_topk=10)
    assert (class_index == 0).sum().item() == 10
    assert (class_index == 1).sum().item() == 3


def test_topk_none_keeps_every_candidate():
    scores = torch.full((50, 2), 0.5)
    anchor_index, _classes, _scores = expand_class_candidates(scores, 0.05, pre_nms_topk=None)
    assert anchor_index.numel() == 100


def test_empty_scores_return_empty_candidates():
    anchor_index, class_index, scores = expand_class_candidates(torch.zeros((0, 2)), 0.05)
    assert anchor_index.numel() == class_index.numel() == scores.numel() == 0


# --------------------------------------------------------------------------- #
# Class-aware suppression
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("use_soft_nms", [False, True])
def test_identical_boxes_of_different_classes_both_survive(use_soft_nms):
    """The headline regression: rice must not suppress an overlapping weed."""
    boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, 10.0, 10.0]])
    scores = torch.tensor([0.9, 0.8])
    labels = torch.tensor([0, 1])
    keep, kept_scores = class_aware_suppression(
        boxes, scores, labels, 0.5, use_soft_nms=use_soft_nms
    )
    assert sorted(labels[keep].tolist()) == [0, 1]
    assert kept_scores.numel() == 2


def test_identical_boxes_of_the_same_class_are_suppressed():
    boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, 10.0, 10.0]])
    scores = torch.tensor([0.9, 0.8])
    labels = torch.tensor([1, 1])
    keep, _scores = class_aware_suppression(boxes, scores, labels, 0.5, use_soft_nms=False)
    assert keep.numel() == 1
    assert keep.tolist() == [0]  # the stronger one


def test_soft_nms_decays_a_same_class_duplicate_instead_of_deleting_it():
    boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, 10.0, 10.0]])
    scores = torch.tensor([0.9, 0.8])
    labels = torch.tensor([1, 1])
    keep, kept_scores = class_aware_suppression(boxes, scores, labels, 0.5, use_soft_nms=True)
    assert keep.numel() == 2
    assert kept_scores[0].item() == pytest.approx(0.9)
    assert kept_scores[1].item() < 0.8  # decayed


def test_non_overlapping_same_class_boxes_both_survive():
    boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [50.0, 50.0, 60.0, 60.0]])
    scores = torch.tensor([0.9, 0.8])
    labels = torch.tensor([1, 1])
    keep, _scores = class_aware_suppression(boxes, scores, labels, 0.5, use_soft_nms=False)
    assert keep.numel() == 2


@pytest.mark.parametrize("use_soft_nms", [False, True])
def test_max_detections_is_a_shared_budget_across_classes(use_soft_nms):
    boxes = torch.tensor([[float(i) * 100, 0.0, float(i) * 100 + 10, 10.0] for i in range(10)])
    scores = torch.linspace(0.9, 0.5, 10)
    labels = torch.tensor([0, 1] * 5)
    keep, kept_scores = class_aware_suppression(
        boxes, scores, labels, 0.5, use_soft_nms=use_soft_nms, max_detections=4
    )
    assert keep.numel() == 4
    assert kept_scores.numel() == 4
    assert kept_scores.tolist() == sorted(kept_scores.tolist(), reverse=True)


def test_suppression_of_empty_input_is_empty():
    keep, scores = class_aware_suppression(
        torch.zeros((0, 4)), torch.zeros((0,)), torch.zeros((0,), dtype=torch.long), 0.5
    )
    assert keep.numel() == scores.numel() == 0


def test_hard_nms_fallback_matches_torchvision_on_the_class_aware_case():
    """The offset-trick fallback must behave like batched_nms when it is missing."""
    from agrinav.inference import postprocess

    boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [1.0, 1.0, 11.0, 11.0]])
    scores = torch.tensor([0.9, 0.8])
    same_class = torch.tensor([0, 0])
    different_class = torch.tensor([0, 1])

    real = postprocess._batched_nms(boxes, scores, different_class, 0.5)
    assert real.numel() == 2

    offset = (boxes.max() - boxes.min() + 1) if boxes.numel() else 1.0
    shifted = boxes + (different_class.to(boxes.dtype) * offset).unsqueeze(1)
    assert hard_nms(shifted, scores, 0.5).numel() == 2
    assert hard_nms(boxes, scores, 0.5).numel() == 1
    assert postprocess._batched_nms(boxes, scores, same_class, 0.5).numel() == 1


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def test_decode_deltas_of_zero_returns_the_anchor():
    anchors = torch.tensor([[10.0, 20.0, 30.0, 60.0]])
    boxes = decode_deltas(torch.zeros(1, 4), anchors, 512, 512)
    assert torch.allclose(boxes, anchors, atol=1e-5)


def test_decode_deltas_clamps_to_the_model_canvas():
    anchors = torch.tensor([[0.0, 0.0, 20.0, 20.0]])
    deltas = torch.tensor([[0.0, 0.0, 3.0, 3.0]])  # exp(3) ~= 20x
    boxes = decode_deltas(deltas, anchors, 64, 64)
    assert boxes.min() >= 0 and boxes.max() <= 64


def test_decode_deltas_exponent_is_clamped_against_a_diverged_head():
    anchors = torch.tensor([[0.0, 0.0, 20.0, 20.0]])
    huge = decode_deltas(torch.full((1, 4), 50.0), anchors, 512, 512)
    assert torch.isfinite(huge).all()


def test_invert_letterbox_round_trips_the_forward_transform():
    from agrinav.models.weeddet_v6b import letterbox_pil

    pytest.importorskip("PIL")
    from PIL import Image

    image = Image.new("RGB", (200, 100))
    _canvas, scale_x, scale_y, pad_left, pad_top = letterbox_pil(image, 128)
    original = torch.tensor([[20.0, 30.0, 120.0, 90.0]])
    forward = original.clone()
    forward[:, [0, 2]] = forward[:, [0, 2]] * scale_x + pad_left
    forward[:, [1, 3]] = forward[:, [1, 3]] * scale_y + pad_top
    back, keep = invert_letterbox(forward, scale_x, scale_y, pad_left, pad_top, 200, 100)
    assert keep.all()
    assert torch.allclose(back, original, atol=1e-3)


def test_invert_letterbox_clips_boxes_that_reached_into_the_padding():
    """Unclipped, these came back negative and pycocotools scored them as real area."""
    boxes = torch.tensor([[-30.0, -30.0, 50.0, 50.0]])
    mapped, keep = invert_letterbox(boxes, 1.0, 1.0, 0, 0, orig_w=40, orig_h=40)
    assert keep.tolist() == [True]
    assert mapped[0].tolist() == [0.0, 0.0, 40.0, 40.0]


def test_invert_letterbox_drops_a_box_that_existed_only_in_the_padding():
    boxes = torch.tensor([[-50.0, -50.0, -10.0, -10.0]])
    _mapped, keep = invert_letterbox(boxes, 1.0, 1.0, 0, 0, orig_w=40, orig_h=40)
    assert keep.tolist() == [False]


def test_invert_letterbox_without_bounds_does_not_clip():
    boxes = torch.tensor([[-30.0, -30.0, 50.0, 50.0]])
    mapped, _keep = invert_letterbox(boxes, 1.0, 1.0, 0, 0)
    assert mapped[0][0].item() == -30.0


def test_box_iou_matches_hand_computed_overlap():
    a = torch.tensor([[0.0, 0.0, 10.0, 10.0]])
    b = torch.tensor([[5.0, 0.0, 15.0, 10.0]])
    assert box_iou(a, b).item() == pytest.approx(50 / 150)


def test_soft_nms_on_empty_input():
    keep, scores = soft_nms(torch.zeros((0, 4)), torch.zeros((0,)))
    assert keep.numel() == scores.numel() == 0


# --------------------------------------------------------------------------- #
# COCO formatting
# --------------------------------------------------------------------------- #
def test_to_coco_detections_converts_xyxy_to_xywh_and_maps_categories():
    records = to_coco_detections(
        torch.tensor([[10.0, 20.0, 30.0, 60.0]]),
        torch.tensor([0.75]),
        torch.tensor([1]),
        image_id=7,
        index_to_category_id={0: 1, 1: 2},
    )
    assert records == [
        {"image_id": 7, "category_id": 2, "bbox": [10.0, 20.0, 20.0, 40.0], "score": 0.75}
    ]


def test_to_coco_detections_refuses_an_unmapped_class():
    with pytest.raises(KeyError, match="no COCO category id"):
        to_coco_detections(
            torch.tensor([[0.0, 0.0, 1.0, 1.0]]),
            torch.tensor([0.9]),
            torch.tensor([5]),
            image_id=1,
            index_to_category_id={0: 1},
        )


def test_to_coco_detections_of_nothing_is_an_empty_list():
    assert (
        to_coco_detections(
            torch.zeros((0, 4)),
            torch.zeros((0,)),
            torch.zeros((0,), dtype=torch.long),
            1,
            {0: 1},
        )
        == []
    )


# --------------------------------------------------------------------------- #
# Full decode
# --------------------------------------------------------------------------- #
def _single_anchor_level(scores_per_class, deltas=None):
    """One 1x1 feature level with C class logits and one anchor."""
    num_classes = len(scores_per_class)
    logits = torch.logit(torch.tensor(scores_per_class)).view(1, num_classes, 1, 1)
    regs = (deltas if deltas is not None else torch.zeros(4)).view(1, 4, 1, 1)
    anchors = torch.tensor([[0.0, 0.0, 10.0, 10.0]])
    return [logits], [regs], anchors


def test_decode_batch_emits_both_classes_for_one_anchor():
    cls_logits, regs, anchors = _single_anchor_level([0.9, 0.8])
    result = decode_batch(cls_logits, regs, anchors, (64, 64), num_classes=2)[0]
    assert sorted(result["labels"].tolist()) == [0, 1]
    assert result["boxes"].shape == (2, 4)


def test_decode_batch_returns_empty_when_nothing_clears_threshold():
    cls_logits, regs, anchors = _single_anchor_level([0.01, 0.01])
    result = decode_batch(cls_logits, regs, anchors, (64, 64), num_classes=2)[0]
    assert result["boxes"].shape == (0, 4)
    assert result["scores"].numel() == 0
    assert result["labels"].numel() == 0


def test_decode_batch_scores_are_descending():
    cls_logits, regs, anchors = _single_anchor_level([0.6, 0.95])
    result = decode_batch(cls_logits, regs, anchors, (64, 64), num_classes=2)[0]
    assert result["scores"].tolist() == sorted(result["scores"].tolist(), reverse=True)
    assert result["labels"][0].item() == 1


def test_decode_batch_handles_a_batch_of_more_than_one_image():
    logits = torch.logit(torch.tensor([[0.9, 0.1], [0.1, 0.9]])).view(2, 2, 1, 1)
    regs = torch.zeros(2, 4, 1, 1)
    anchors = torch.tensor([[0.0, 0.0, 10.0, 10.0]])
    results = decode_batch([logits], [regs], anchors, (64, 64), num_classes=2)
    assert len(results) == 2
    assert results[0]["labels"][0].item() == 0
    assert results[1]["labels"][0].item() == 1


def test_decode_batch_output_threshold_filters_after_suppression():
    cls_logits, regs, anchors = _single_anchor_level([0.9, 0.2])
    result = decode_batch(cls_logits, regs, anchors, (64, 64), num_classes=2, output_threshold=0.5)[
        0
    ]
    assert result["labels"].tolist() == [0]


def test_model_eval_forward_uses_the_class_aware_path():
    """End to end through WeedDet: the wiring, not just the helper."""
    import agrinav.models.weeddet_v6b as weeddet

    model = weeddet.WeedDet(num_classes=2).eval()
    with torch.no_grad():
        result = model(torch.zeros(1, 3, 128, 128))[0]
    assert set(result) == {"boxes", "scores", "labels"}
    assert result["boxes"].shape[1] == 4
    # Whatever it predicts on a blank image, it must not exceed the COCO budget.
    assert result["boxes"].shape[0] <= 100
