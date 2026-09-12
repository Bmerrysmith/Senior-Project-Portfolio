"""The one canonical detection postprocessor: raw head outputs to scored boxes.

Training, evaluation, and any future runtime must share this path. Three
protocols drifting apart is how a detector ends up with numbers nobody can
reproduce, and the July-29 audit found exactly that risk here.

What this fixes
---------------
The previous decode kept **one class per anchor** (``sigmoid().max(dim=1)``) and
then ran a **single class-agnostic** Soft-NMS/NMS pass over everything that
survived. Two consequences, both silent:

1. an anchor that fired on rice *and* weed contributed only its stronger class —
   the alternative hypothesis was discarded before any metric could see it;
2. a rice box could suppress an overlapping weed box, and vice versa, which in a
   rice paddy is not an edge case.

Here, every ``(anchor, class)`` pair above threshold becomes its own candidate,
and suppression is applied **within** a class and never across classes.

Top-k is applied **per class**, not globally. With a 6.8:1 rice-to-weed instance
ratio, a global cap is a cap the majority class wins: rice candidates can fill it
and evict weed candidates that were above threshold. Per-class top-k costs
nothing and removes that failure mode.

Coordinate conventions
----------------------
``decode_deltas`` and ``decode_batch`` work in **letterboxed model space**
(``img_shape``). :func:`invert_letterbox` maps back to original image pixels and
clips there — the inverse transform is the only place that is allowed to know
about padding.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import torch

# Pre-NMS score gate. 0.05 is the COCO convention: low enough that the
# precision-recall curve is not truncated before the metric sees it.
DEFAULT_SCORE_THRESHOLD = 0.05
# IoU threshold for suppression within a class.
DEFAULT_NMS_IOU = 0.50
# Candidates kept per class before suppression.
DEFAULT_PRE_NMS_TOPK = 2000
# Detections kept per image after suppression. 100 is the COCO standard; keeping
# the decode default aligned with the metric default avoids a silent protocol
# mismatch between what is produced and what is scored.
DEFAULT_MAX_DETECTIONS = 100
# Width/height regression is exponential; clamp the exponent so a diverged head
# cannot produce inf-sized boxes during early training.
DELTA_EXP_CLAMP = 4.0


# --------------------------------------------------------------------------- #
# Geometry primitives
# --------------------------------------------------------------------------- #
def box_iou(boxes1: torch.Tensor, boxes2: torch.Tensor, eps: float = 1e-7) -> torch.Tensor:
    """Pairwise IoU between two sets of xyxy boxes. Returns ``(N, M)``."""
    area1 = (boxes1[:, 2] - boxes1[:, 0]).clamp(min=0) * (boxes1[:, 3] - boxes1[:, 1]).clamp(min=0)
    area2 = (boxes2[:, 2] - boxes2[:, 0]).clamp(min=0) * (boxes2[:, 3] - boxes2[:, 1]).clamp(min=0)
    lt = torch.max(boxes1[:, None, :2], boxes2[None, :, :2])
    rb = torch.min(boxes1[:, None, 2:], boxes2[None, :, 2:])
    wh = (rb - lt).clamp(min=0)
    inter = wh[..., 0] * wh[..., 1]
    return inter / (area1[:, None] + area2[None, :] - inter + eps)


def hard_nms(boxes: torch.Tensor, scores: torch.Tensor, iou_threshold: float) -> torch.Tensor:
    """Greedy NMS in pure torch. Returns kept indices, highest score first.

    Used only when ``torchvision.ops`` is unavailable; the torchvision kernels are
    preferred because they are the reference implementation everyone else scores
    against.
    """
    if boxes.numel() == 0:
        return torch.empty((0,), dtype=torch.long, device=boxes.device)
    order = scores.argsort(descending=True)
    keep: list[torch.Tensor] = []
    while order.numel() > 0:
        current = order[0]
        keep.append(current)
        if order.numel() == 1:
            break
        ious = box_iou(boxes[current].unsqueeze(0), boxes[order[1:]]).squeeze(0)
        order = order[1:][ious <= iou_threshold]
    return torch.stack(keep) if keep else torch.empty((0,), dtype=torch.long, device=boxes.device)


def soft_nms(
    boxes: torch.Tensor,
    scores: torch.Tensor,
    iou_threshold: float = DEFAULT_NMS_IOU,
    sigma: float = 0.5,
    score_threshold: float = 0.001,
    max_dets: int = 1000,
    method: str = "gaussian",
) -> tuple[torch.Tensor, torch.Tensor]:
    """Soft-NMS: decay overlapping scores instead of deleting them.

    Suited to dense scenes where true objects genuinely overlap — a rice canopy
    being the motivating case.

    Args:
        boxes: ``(N, 4)`` xyxy.
        scores: ``(N,)``.
        iou_threshold: overlap above which linear/hard decay applies. The
            ``gaussian`` method decays continuously and ignores this.
        sigma: gaussian decay width.
        score_threshold: stop once the best remaining score falls below this.
        max_dets: stop after this many kept boxes.
        method: ``gaussian`` | ``linear`` | ``hard``.

    Returns:
        ``(kept_indices, decayed_scores)`` — the scores are the *decayed* values
        for the kept boxes, not the originals.
    """
    if boxes.numel() == 0:
        empty = torch.empty((0,), dtype=torch.long, device=boxes.device)
        return empty, scores.new_zeros((0,))

    boxes_work = boxes.clone()
    scores_work = scores.clone()
    indices = torch.arange(scores.shape[0], device=boxes.device)
    keep: list[torch.Tensor] = []
    keep_scores: list[torch.Tensor] = []

    while indices.numel() > 0 and len(keep) < max_dets:
        best = torch.argmax(scores_work)
        best_score = scores_work[best]
        if best_score < score_threshold:
            break
        keep.append(indices[best])
        keep_scores.append(best_score)
        if indices.numel() == 1:
            break

        current = boxes_work[best].unsqueeze(0)
        remaining = torch.ones(indices.numel(), dtype=torch.bool, device=boxes.device)
        remaining[best] = False
        boxes_work = boxes_work[remaining]
        scores_work = scores_work[remaining]
        indices = indices[remaining]

        ious = box_iou(current, boxes_work).squeeze(0)
        if method == "linear":
            decay = torch.where(ious > iou_threshold, 1 - ious, torch.ones_like(ious))
        elif method == "hard":
            decay = torch.where(ious > iou_threshold, torch.zeros_like(ious), torch.ones_like(ious))
        else:
            decay = torch.exp(-(ious * ious) / sigma)
        scores_work = scores_work * decay

    if not keep:
        empty = torch.empty((0,), dtype=torch.long, device=boxes.device)
        return empty, scores.new_zeros((0,))
    return torch.stack(keep), torch.stack(keep_scores)


# --------------------------------------------------------------------------- #
# Decode
# --------------------------------------------------------------------------- #
def decode_deltas(
    deltas: torch.Tensor,
    anchors: torch.Tensor,
    img_h: int,
    img_w: int,
) -> torch.Tensor:
    """Apply regression deltas to anchors and clamp to the model input canvas.

    Args:
        deltas: ``(N, 4)`` as ``(dx, dy, dw, dh)`` — centre offsets normalized by
            anchor size, log-space size ratios.
        anchors: ``(N, 4)`` xyxy.
        img_h: model input height (letterboxed).
        img_w: model input width (letterboxed).

    Returns:
        ``(N, 4)`` xyxy boxes in letterboxed model space.
    """
    anchor_w = anchors[:, 2] - anchors[:, 0]
    anchor_h = anchors[:, 3] - anchors[:, 1]
    anchor_cx = (anchors[:, 0] + anchors[:, 2]) * 0.5
    anchor_cy = (anchors[:, 1] + anchors[:, 3]) * 0.5

    cx = deltas[:, 0] * anchor_w + anchor_cx
    cy = deltas[:, 1] * anchor_h + anchor_cy
    width = torch.exp(deltas[:, 2].clamp(max=DELTA_EXP_CLAMP)) * anchor_w
    height = torch.exp(deltas[:, 3].clamp(max=DELTA_EXP_CLAMP)) * anchor_h

    return torch.stack(
        [
            (cx - width / 2).clamp(0, img_w),
            (cy - height / 2).clamp(0, img_h),
            (cx + width / 2).clamp(0, img_w),
            (cy + height / 2).clamp(0, img_h),
        ],
        dim=1,
    )


def expand_class_candidates(
    scores: torch.Tensor,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    pre_nms_topk: int | None = DEFAULT_PRE_NMS_TOPK,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Turn per-anchor class scores into independent ``(anchor, class)`` candidates.

    This is the fix for the discarded-hypothesis half of the decode bug: an anchor
    scoring 0.7 rice and 0.6 weed yields **two** candidates, so a metric can see
    both and suppression can resolve them per class.

    Top-k is per class (see the module docstring): with a 6.8:1 class imbalance a
    global cap is one the majority class wins.

    Args:
        scores: ``(N, C)`` **probabilities** (sigmoid already applied).
        score_threshold: keep candidates strictly above this.
        pre_nms_topk: per-class candidate cap; ``None`` disables it.

    Returns:
        ``(anchor_index, class_index, score)``, each 1-D and index-aligned,
        sorted by descending score.
    """
    if scores.numel() == 0:
        empty_long = torch.empty((0,), dtype=torch.long, device=scores.device)
        return empty_long, empty_long.clone(), scores.new_zeros((0,))

    above = scores > score_threshold
    anchor_index, class_index = above.nonzero(as_tuple=True)
    candidate_scores = scores[anchor_index, class_index]

    if pre_nms_topk is not None and candidate_scores.numel() > pre_nms_topk:
        keep_mask = torch.zeros_like(candidate_scores, dtype=torch.bool)
        for class_id in class_index.unique():
            in_class = (class_index == class_id).nonzero(as_tuple=True)[0]
            if in_class.numel() > pre_nms_topk:
                top = candidate_scores[in_class].topk(pre_nms_topk).indices
                in_class = in_class[top]
            keep_mask[in_class] = True
        anchor_index = anchor_index[keep_mask]
        class_index = class_index[keep_mask]
        candidate_scores = candidate_scores[keep_mask]

    order = candidate_scores.argsort(descending=True)
    return anchor_index[order], class_index[order], candidate_scores[order]


def class_aware_suppression(
    boxes: torch.Tensor,
    scores: torch.Tensor,
    labels: torch.Tensor,
    iou_threshold: float = DEFAULT_NMS_IOU,
    *,
    use_soft_nms: bool = True,
    soft_nms_sigma: float = 0.5,
    score_threshold: float = 0.001,
    max_detections: int = DEFAULT_MAX_DETECTIONS,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Suppress overlaps **within** each class, never across classes.

    A rice detection and a weed detection on the same pixels are competing
    hypotheses for a *metric* to arbitrate, not for NMS to silently resolve.

    Hard NMS uses ``torchvision.ops.batched_nms`` when available — it is the
    reference implementation and explicitly does not suppress between categories.
    Soft-NMS has no batched kernel, so it is run per class in a loop.

    Args:
        boxes: ``(N, 4)`` xyxy.
        scores: ``(N,)``.
        labels: ``(N,)`` integer class indices.
        iou_threshold: suppression IoU.
        use_soft_nms: decay overlapping scores instead of deleting them.
        soft_nms_sigma: gaussian decay width for Soft-NMS.
        score_threshold: Soft-NMS stopping score.
        max_detections: cap on the returned detections, applied **after**
            merging classes so the cap is shared, exactly as COCO's ``maxDets``.

    Returns:
        ``(kept_indices, scores_for_kept)`` sorted by descending score.
        ``scores_for_kept`` are Soft-NMS-decayed values when Soft-NMS is used.
    """
    if boxes.numel() == 0:
        empty = torch.empty((0,), dtype=torch.long, device=boxes.device)
        return empty, scores.new_zeros((0,))

    if not use_soft_nms:
        keep = _batched_nms(boxes, scores, labels, iou_threshold)
        keep = keep[:max_detections]
        return keep, scores[keep]

    kept_indices: list[torch.Tensor] = []
    kept_scores: list[torch.Tensor] = []
    for class_id in labels.unique():
        in_class = (labels == class_id).nonzero(as_tuple=True)[0]
        local_keep, local_scores = soft_nms(
            boxes[in_class],
            scores[in_class],
            iou_threshold=iou_threshold,
            sigma=soft_nms_sigma,
            score_threshold=score_threshold,
            # Per class, then cap globally below: a class must not be able to
            # exhaust the budget before another class is considered.
            max_dets=max_detections,
        )
        kept_indices.append(in_class[local_keep])
        kept_scores.append(local_scores)

    if not kept_indices:
        empty = torch.empty((0,), dtype=torch.long, device=boxes.device)
        return empty, scores.new_zeros((0,))

    merged_indices = torch.cat(kept_indices)
    merged_scores = torch.cat(kept_scores)
    order = merged_scores.argsort(descending=True)[:max_detections]
    return merged_indices[order], merged_scores[order]


def _batched_nms(
    boxes: torch.Tensor, scores: torch.Tensor, labels: torch.Tensor, iou_threshold: float
) -> torch.Tensor:
    """``torchvision.ops.batched_nms`` when importable, else an equivalent fallback.

    The fallback reproduces torchvision's coordinate-offset trick: shifting each
    class into its own disjoint region of the plane makes a single NMS pass
    class-aware, because boxes of different classes can no longer overlap.
    """
    try:
        from torchvision.ops import batched_nms
    except ImportError:
        offset = (boxes.max() - boxes.min() + 1) if boxes.numel() else 1.0
        shifted = boxes + (labels.to(boxes.dtype) * offset).unsqueeze(1)
        return hard_nms(shifted, scores, iou_threshold)
    return batched_nms(boxes, scores, labels.to(torch.int64), iou_threshold)


def decode_batch(
    cls_logits: Sequence[torch.Tensor],
    regs: Sequence[torch.Tensor],
    anchors: torch.Tensor,
    img_shape: tuple[int, int],
    *,
    num_classes: int,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    nms_iou: float = DEFAULT_NMS_IOU,
    max_detections: int = DEFAULT_MAX_DETECTIONS,
    output_threshold: float | None = None,
    use_soft_nms: bool = True,
    soft_nms_sigma: float = 0.5,
    pre_nms_topk: int | None = DEFAULT_PRE_NMS_TOPK,
) -> list[dict[str, torch.Tensor]]:
    """Decode one batch of head outputs into per-image detections.

    Args:
        cls_logits: per-level ``(B, C, H, W)`` **logits** (sigmoid applied here).
        regs: per-level ``(B, 4, H, W)`` deltas.
        anchors: ``(N, 4)`` xyxy anchors, concatenated across levels in the same
            order the level tensors are flattened.
        img_shape: ``(height, width)`` of the letterboxed model input.
        num_classes: number of classes the head predicts.
        score_threshold: pre-suppression candidate gate.
        nms_iou: suppression IoU threshold.
        max_detections: per-image cap after suppression.
        output_threshold: optional gate applied *after* suppression. Defaults to
            ``score_threshold``. With Soft-NMS this is meaningful, because scores
            are decayed rather than boxes deleted.
        use_soft_nms: use Soft-NMS instead of hard NMS.
        soft_nms_sigma: gaussian decay width.
        pre_nms_topk: per-class candidate cap.

    Returns:
        One dict per batch item with ``boxes`` ``(K, 4)`` xyxy in letterboxed
        model space, ``scores`` ``(K,)``, ``labels`` ``(K,)`` — all sorted by
        descending score.
    """
    if output_threshold is None:
        output_threshold = score_threshold

    batch_size = cls_logits[0].shape[0]
    height, width = img_shape

    flat_cls = torch.cat(
        [level.permute(0, 2, 3, 1).reshape(batch_size, -1, num_classes) for level in cls_logits],
        dim=1,
    )
    flat_reg = torch.cat(
        [level.permute(0, 2, 3, 1).reshape(batch_size, -1, 4) for level in regs], dim=1
    )

    results: list[dict[str, torch.Tensor]] = []
    for index in range(batch_size):
        probabilities = flat_cls[index].sigmoid()
        anchor_index, class_index, scores = expand_class_candidates(
            probabilities, score_threshold=score_threshold, pre_nms_topk=pre_nms_topk
        )
        if anchor_index.numel() == 0:
            results.append(_empty_result(flat_cls))
            continue

        boxes = decode_deltas(flat_reg[index][anchor_index], anchors[anchor_index], height, width)
        keep, kept_scores = class_aware_suppression(
            boxes,
            scores,
            class_index,
            iou_threshold=nms_iou,
            use_soft_nms=use_soft_nms,
            soft_nms_sigma=soft_nms_sigma,
            max_detections=max_detections,
        )
        final = kept_scores > output_threshold
        results.append(
            {
                "boxes": boxes[keep][final],
                "scores": kept_scores[final],
                "labels": class_index[keep][final],
            }
        )
    return results


def _empty_result(reference: torch.Tensor) -> dict[str, torch.Tensor]:
    return {
        "boxes": reference.new_zeros((0, 4)),
        "scores": reference.new_zeros((0,)),
        "labels": torch.empty((0,), dtype=torch.long, device=reference.device),
    }


# --------------------------------------------------------------------------- #
# Inverse transform and COCO formatting
# --------------------------------------------------------------------------- #
def invert_letterbox(
    boxes: torch.Tensor,
    scale_x: float,
    scale_y: float,
    pad_left: int,
    pad_top: int,
    orig_w: int | None = None,
    orig_h: int | None = None,
    min_side: float = 1e-3,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Map letterboxed boxes back to original image pixels, clipped to bounds.

    The clip is the point. Detections that extended into the grey padding used to
    come back as negative coordinates or beyond the original dimensions, which
    ``pycocotools`` scores as real area outside the image.

    Args:
        boxes: ``(N, 4)`` xyxy in letterboxed space.
        scale_x: x scale applied by the forward letterbox.
        scale_y: y scale applied by the forward letterbox.
        pad_left: left padding added by the forward letterbox.
        pad_top: top padding added by the forward letterbox.
        orig_w: original width; clipping is skipped when omitted.
        orig_h: original height; clipping is skipped when omitted.
        min_side: boxes thinner than this after clipping are dropped — a box that
            existed only inside the padding is not a detection.

    Returns:
        ``(boxes_in_original_pixels, keep_mask)``. Apply ``keep_mask`` to the
        matching scores and labels.
    """
    mapped = boxes.clone().float()
    mapped[:, [0, 2]] -= pad_left
    mapped[:, [1, 3]] -= pad_top
    mapped[:, [0, 2]] /= scale_x
    mapped[:, [1, 3]] /= scale_y

    if orig_w is not None and orig_h is not None:
        mapped[:, [0, 2]] = mapped[:, [0, 2]].clamp(0, float(orig_w))
        mapped[:, [1, 3]] = mapped[:, [1, 3]].clamp(0, float(orig_h))

    widths = mapped[:, 2] - mapped[:, 0]
    heights = mapped[:, 3] - mapped[:, 1]
    keep = (widths > min_side) & (heights > min_side)
    return mapped, keep


def to_coco_detections(
    boxes: torch.Tensor,
    scores: torch.Tensor,
    labels: torch.Tensor,
    image_id: Any,
    index_to_category_id: Mapping[int, int],
) -> list[dict[str, Any]]:
    """Format detections as COCO result records.

    Args:
        boxes: ``(N, 4)`` xyxy in **original image** pixels.
        scores: ``(N,)``.
        labels: ``(N,)`` contiguous class **indices** as the model emits them.
        image_id: the ground-truth image id these belong to.
        index_to_category_id: model class index to COCO category id. Every label
            must be present — a missing entry is a class-map bug, so it raises
            rather than dropping the detection.

    Returns:
        ``[{"image_id", "category_id", "bbox": [x, y, w, h], "score"}, ...]``.

    Raises:
        KeyError: if a predicted label has no category id.
    """
    records: list[dict[str, Any]] = []
    for box, score, label in zip(boxes.tolist(), scores.tolist(), labels.tolist()):
        index = int(label)
        if index not in index_to_category_id:
            raise KeyError(
                f"predicted class index {index} has no COCO category id "
                f"(map covers {sorted(index_to_category_id)}). The class map used for "
                "inference must match the one the checkpoint was trained with."
            )
        x1, y1, x2, y2 = box
        records.append(
            {
                "image_id": image_id,
                "category_id": int(index_to_category_id[index]),
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "score": float(score),
            }
        )
    return records
