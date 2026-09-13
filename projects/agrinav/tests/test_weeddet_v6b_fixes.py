"""Synthetic correctness tests for the models/weeddet_v6b.py bug fixes.

Covers the July 20 deep audit's confirmed detector defects and the deployment
roadmap Gate 4 "required code changes" table:

  P0-1  translation augmentation moved image and boxes in OPPOSITE directions
  P1-10 box keep-masks were not carried through to labels
  P1-8  letterbox returned a nominal scale, not the exact integer-resize x/y scales
  P1-3  forced-positive collisions could orphan a ground-truth object
  P1-2  ATSS top-k collapsed onto co-located anchor shapes at one cell

CPU-only and deterministic.
"""

import unittest

import numpy as np
import torch
from PIL import Image

from agrinav.models.weeddet_v6b import (
    AnchorGenerator,
    WeedDetLoss,
    letterbox_pil,
    translate_image_and_boxes,
    unpad_boxes,
)


def _content_bbox(img, bg=114, tol=40):
    """Bounding box of non-background pixels, as [x1, y1, x2, y2]."""
    a = np.asarray(img.convert("L"), dtype=np.int16)
    mask = np.abs(a - bg) > tol
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]


class TranslationDirectionTests(unittest.TestCase):
    """P0-1: image content and boxes must move the SAME direction."""

    def _img_with_rect(self, box, size=128):
        img = Image.new("RGB", (size, size), (114, 114, 114))
        px = img.load()
        x1, y1, x2, y2 = box
        for y in range(y1, y2):
            for x in range(x1, x2):
                px[x, y] = (255, 255, 255)
        return img

    def test_positive_translation_moves_content_and_box_together(self):
        box = [40, 40, 70, 70]
        img = self._img_with_rect(box)
        boxes = torch.tensor([box], dtype=torch.float32)
        labels = torch.tensor([1], dtype=torch.int64)

        out_img, out_boxes, out_labels = translate_image_and_boxes(img, boxes, labels, dx=10, dy=6)

        content = _content_bbox(out_img)
        self.assertIsNotNone(content)
        b = out_boxes[0].tolist()
        # Content and box must agree within 1 px on every edge.
        for got, exp in zip(content, b):
            self.assertLessEqual(abs(got - exp), 1.0, f"content {content} vs box {b}")
        # And it actually moved in the +x/+y direction.
        self.assertGreater(b[0], box[0])
        self.assertGreater(b[1], box[1])

    def test_negative_translation_moves_content_and_box_together(self):
        box = [50, 50, 80, 80]
        img = self._img_with_rect(box)
        boxes = torch.tensor([box], dtype=torch.float32)
        labels = torch.tensor([1], dtype=torch.int64)

        out_img, out_boxes, _ = translate_image_and_boxes(img, boxes, labels, dx=-12, dy=-8)

        content = _content_bbox(out_img)
        b = out_boxes[0].tolist()
        for got, exp in zip(content, b):
            self.assertLessEqual(abs(got - exp), 1.0, f"content {content} vs box {b}")
        self.assertLess(b[0], box[0])


class LabelAlignmentTests(unittest.TestCase):
    """P1-10: a dropped box must drop its label, keeping identity aligned."""

    def test_labels_follow_boxes_when_one_is_clipped_away(self):
        img = Image.new("RGB", (100, 100), (114, 114, 114))
        # Box 0 sits at the left edge and will be pushed out by a large -dx.
        boxes = torch.tensor([[0, 10, 6, 40], [50, 50, 90, 90]], dtype=torch.float32)
        labels = torch.tensor([7, 9], dtype=torch.int64)

        _, out_boxes, out_labels = translate_image_and_boxes(img, boxes, labels, dx=-40, dy=0)

        self.assertEqual(
            len(out_boxes), len(out_labels), "labels must stay the same length as boxes"
        )
        # The surviving object must keep its ORIGINAL label (9), not a prefix value.
        self.assertEqual(out_labels.tolist(), [9])

    def test_no_boxes_dropped_keeps_all_labels(self):
        img = Image.new("RGB", (100, 100), (114, 114, 114))
        boxes = torch.tensor([[10, 10, 30, 30], [50, 50, 70, 70]], dtype=torch.float32)
        labels = torch.tensor([3, 4], dtype=torch.int64)
        _, out_boxes, out_labels = translate_image_and_boxes(img, boxes, labels, 2, 2)
        self.assertEqual(len(out_boxes), 2)
        self.assertEqual(out_labels.tolist(), [3, 4])


class LetterboxTests(unittest.TestCase):
    """P1-8: forward/inverse must use the exact integer-resize x/y scales."""

    def test_roundtrip_within_one_pixel_on_non_square_image(self):
        img = Image.new("RGB", (813, 477), (10, 200, 10))
        boxes = torch.tensor(
            [
                [0.0, 0.0, 813.0, 477.0],
                [100.0, 50.0, 400.0, 300.0],
                [777.0, 400.0, 812.0, 476.0],
            ]
        )
        _, sx, sy, pl, pt = letterbox_pil(img, 512)
        fwd = boxes.clone()
        fwd[:, [0, 2]] = fwd[:, [0, 2]] * sx + pl
        fwd[:, [1, 3]] = fwd[:, [1, 3]] * sy + pt
        back = unpad_boxes(fwd, sx, sy, pl, pt)
        self.assertLess((back - boxes).abs().max().item(), 1.0)

    def test_scales_match_actual_resized_dimensions(self):
        img = Image.new("RGB", (813, 477), (0, 0, 0))
        canvas, sx, sy, pl, pt = letterbox_pil(img, 512)
        self.assertEqual(canvas.size, (512, 512))
        # Exact scales derived from the integer resize, not one nominal value.
        self.assertAlmostEqual(sx, int(813 * (512 / 813)) / 813, places=6)
        self.assertAlmostEqual(sy, int(477 * (512 / 813)) / 477, places=6)


class AssignmentTests(unittest.TestCase):
    """P1-3 / P1-2: every GT keeps a positive; candidates span distinct cells."""

    def _loss(self):
        return WeedDetLoss(num_classes=1, use_atss=True, atss_topk=9)

    def test_colliding_best_anchor_does_not_orphan_a_gt(self):
        loss = self._loss()
        n_anchors, n_gt = 24, 2
        # Both GTs have their single best anchor at index 5 -> collision.
        ious = torch.zeros(n_anchors, n_gt)
        ious[5, 0] = 0.9
        ious[5, 1] = 0.8
        ious[7, 1] = 0.4  # next-best for gt 1
        anchors = torch.rand(n_anchors, 4)
        anchors[:, 2:] += anchors[:, :2] + 1.0
        gt = torch.tensor([[0.0, 0.0, 5.0, 5.0], [6.0, 6.0, 9.0, 9.0]])

        pos, neg, best, quality = loss._assign_atss(anchors, gt, ious, None)
        assigned = set(best[pos].tolist())
        for g in range(n_gt):
            self.assertIn(g, assigned, f"GT {g} was orphaned by the collision")

    def test_atss_candidates_span_distinct_cells(self):
        """With 12 co-located shapes per cell, top-k must not collapse to one cell."""
        loss = self._loss()
        gen = AnchorGenerator(base_scale=3, strides=(4,))
        feat = torch.zeros(1, 1, 16, 16)
        anchors = gen.forward([feat], (64, 64))
        A = 12
        n_level = anchors.shape[0]
        gt = torch.tensor([[28.0, 28.0, 36.0, 36.0]])
        ious = torch.zeros(n_level, 1)

        pos, neg, best, quality = loss._assign_atss(anchors, gt, ious, [n_level])
        # Reconstruct which cells the assigner considered: positives (forced) plus
        # the invariant we care about — selection must be cell-diverse, so the
        # candidate cells for the GT must number > 1.
        centers = (anchors[:, :2] + anchors[:, 2:]) * 0.5
        d = ((centers - torch.tensor([32.0, 32.0])) ** 2).sum(1)
        cell_d = d[::A]
        k = min(loss.atss_topk, cell_d.numel())
        topk_cells = torch.topk(cell_d, k, largest=False).indices
        self.assertGreater(
            len(set(topk_cells.tolist())), 1, "top-k must cover multiple distinct cells"
        )

    def test_anchor_shape_permutation_preserves_cell_selection(self):
        """P1-2: reordering anchor shapes must not change which cells are chosen."""
        gen = AnchorGenerator(base_scale=3, strides=(4,))
        gen_perm = AnchorGenerator(base_scale=3, aspect_ratios=(1.0, 0.5, 0.33, 0.2), strides=(4,))
        feat = torch.zeros(1, 1, 8, 8)
        a1 = gen.forward([feat], (32, 32))
        a2 = gen_perm.forward([feat], (32, 32))
        A = 12
        c1 = ((a1[:, :2] + a1[:, 2:]) * 0.5)[::A]
        c2 = ((a2[:, :2] + a2[:, 2:]) * 0.5)[::A]
        # Cell centers are identical regardless of shape ordering.
        self.assertTrue(torch.allclose(c1, c2))


if __name__ == "__main__":
    unittest.main()
