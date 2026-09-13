"""Tests for the model-to-COCO adapter.

The adapter is the piece that was missing: the repo had a detector and an honest
``pycocotools`` primitive but nothing between them, so no checkpoint was ever
scored on detection quality. The decisive test here drives the whole chain --
decode, inverse letterbox, class mapping, COCO formatting, evaluation -- with a
stub model whose predictions are exactly the ground truth, and asserts AP 1.0.
Anything broken in the geometry or the class map moves that number.
"""

from __future__ import annotations

import json

import pytest
import torch
from PIL import Image

from agrinav.evaluation.runner import EvaluationError, evaluate_split, predict_split, summarize

pytestmark = pytest.mark.unit


class _StubDataset:
    """Minimal stand-in for ``_CocoSplitDataset``: items() plus a class map."""

    def __init__(self, records, catid_to_idx):
        self._records = records
        self.catid_to_idx = catid_to_idx

    def items(self):
        return list(self._records)


class _StubModel(torch.nn.Module):
    """A model that predicts exactly the boxes it is told to, at a fixed score.

    ``_get_logits`` is the seam the runner uses, so the stub implements that and
    nothing else. Anchors are placed *at* the requested boxes in letterboxed
    space and the deltas are zero, which makes the decoded box equal the anchor —
    so any error in the inverse letterbox shows up directly as a lower AP.
    """

    def __init__(
        self, boxes_by_batch_position, labels_by_batch_position, num_classes=2, score=0.99
    ):
        super().__init__()
        self.num_classes = num_classes
        self.boxes = boxes_by_batch_position
        self.labels = labels_by_batch_position
        self.score = score
        self.calls = 0

    def _get_logits(self, images):
        batch = images.shape[0]
        height, width = images.shape[-2:]
        start = self.calls
        self.calls += batch
        per_image = [self.boxes[start + i] for i in range(batch)]
        labels = [self.labels[start + i] for i in range(batch)]
        anchor_count = max(1, max(len(b) for b in per_image))

        anchors = torch.zeros(anchor_count, 4)
        cls = torch.full((batch, self.num_classes, anchor_count, 1), -20.0)
        regs = torch.zeros(batch, 4, anchor_count, 1)
        for image_index, (boxes, image_labels) in enumerate(zip(per_image, labels)):
            for anchor_index, (box, label) in enumerate(zip(boxes, image_labels)):
                anchors[anchor_index] = torch.tensor(box)
                cls[image_index, label, anchor_index, 0] = torch.logit(torch.tensor(self.score))
        return [cls], [regs], anchors, (height, width)


def _write_split(tmp_path, images_spec):
    """Write images + a COCO file. images_spec: [(name, w, h, [(cat_id, xywh)])]."""
    images_root = tmp_path / "images"
    images_root.mkdir(parents=True, exist_ok=True)
    coco = {
        "images": [],
        "annotations": [],
        "categories": [
            {"id": 1, "name": "rice_protect"},
            {"id": 2, "name": "weed_target"},
        ],
    }
    for index, (name, width, height, boxes) in enumerate(images_spec, start=1):
        Image.new("RGB", (width, height), (30, 90, 30)).save(images_root / name)
        coco["images"].append({"id": index, "file_name": name, "width": width, "height": height})
        for category_id, bbox in boxes:
            coco["annotations"].append(
                {
                    "id": len(coco["annotations"]) + 1,
                    "image_id": index,
                    "category_id": category_id,
                    "bbox": list(bbox),
                    "area": bbox[2] * bbox[3],
                    "iscrowd": 0,
                }
            )
    ann_file = tmp_path / "instances_valid.coco.json"
    ann_file.write_text(json.dumps(coco), encoding="utf-8")
    return str(ann_file), str(images_root), coco


def _letterbox_boxes(coco, image_size):
    """Ground-truth boxes expressed in letterboxed model space, as the stub needs."""
    from agrinav.models.weeddet_v6b import letterbox_pil

    per_image, labels_per_image = [], []
    dims = {record["id"]: (record["width"], record["height"]) for record in coco["images"]}
    for record in coco["images"]:
        width, height = dims[record["id"]]
        _canvas, scale_x, scale_y, pad_left, pad_top = letterbox_pil(
            Image.new("RGB", (width, height)), image_size
        )
        boxes, labels = [], []
        for ann in coco["annotations"]:
            if ann["image_id"] != record["id"]:
                continue
            x, y, w, h = ann["bbox"]
            boxes.append(
                [
                    x * scale_x + pad_left,
                    y * scale_y + pad_top,
                    (x + w) * scale_x + pad_left,
                    (y + h) * scale_y + pad_top,
                ]
            )
            labels.append(ann["category_id"] - 1)  # contiguous index
        per_image.append(boxes)
        labels_per_image.append(labels)
    return per_image, labels_per_image


@pytest.fixture
def split(tmp_path):
    spec = [
        ("a.jpg", 200, 100, [(1, [20, 10, 60, 40]), (2, [120, 30, 40, 50])]),
        ("b.jpg", 100, 160, [(1, [10, 20, 50, 60])]),
    ]
    ann_file, images_root, coco = _write_split(tmp_path, spec)
    records = [
        (record["id"], f"{images_root}/{record['file_name']}", record["width"], record["height"])
        for record in coco["images"]
    ]
    dataset = _StubDataset(records, catid_to_idx={1: 0, 2: 1})
    return {"ann_file": ann_file, "dataset": dataset, "coco": coco}


# --------------------------------------------------------------------------- #
def test_perfect_predictions_score_ap_one(split):
    """Whole chain: decode, inverse letterbox, class map, COCO format, evaluate."""
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    model = _StubModel(boxes, labels)
    result, detections, protocol = evaluate_split(
        model, split["dataset"], split["ann_file"], img_size=128, batch_size=1
    )
    assert len(detections) == 3
    assert result.ap == pytest.approx(1.0, abs=1e-6)
    assert result.ap50 == pytest.approx(1.0, abs=1e-6)
    assert result.is_standard_maxdets is True
    assert protocol["max_detections"] == 100
    assert protocol["postprocessor"].endswith("(class-aware)")


def test_shifted_predictions_score_below_one(split):
    """A guard against a test that would pass on any geometry."""
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    shifted = [[[x + 25, y + 25, x2 + 25, y2 + 25] for x, y, x2, y2 in image] for image in boxes]
    model = _StubModel(shifted, labels)
    result, _detections, _protocol = evaluate_split(
        model, split["dataset"], split["ann_file"], img_size=128, batch_size=1
    )
    assert result.ap < 0.9


def test_swapped_class_map_destroys_ap(split):
    """If the class map is wrong, the metric must say so rather than absorb it."""
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    flipped = [[1 - label for label in image] for image in labels]
    model = _StubModel(boxes, flipped)
    result, _detections, _protocol = evaluate_split(
        model, split["dataset"], split["ann_file"], img_size=128, batch_size=1
    )
    assert result.ap < 0.5


def test_predictions_are_inside_the_original_image_bounds(split):
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    # Push every box into the letterbox padding; the inverse transform must clip.
    stretched = [[[x - 40, y - 40, x2 + 40, y2 + 40] for x, y, x2, y2 in im] for im in boxes]
    model = _StubModel(stretched, labels)
    detections = predict_split(model, split["dataset"], img_size=128, batch_size=2)
    dims = {r["id"]: (r["width"], r["height"]) for r in split["coco"]["images"]}
    for record in detections:
        width, height = dims[record["image_id"]]
        x, y, w, h = record["bbox"]
        assert x >= 0 and y >= 0
        assert x + w <= width + 1e-6
        assert y + h <= height + 1e-6
        assert w > 0 and h > 0


def test_detection_records_have_the_coco_shape(split):
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    detections = predict_split(_StubModel(boxes, labels), split["dataset"], img_size=128)
    for record in detections:
        assert set(record) == {"image_id", "category_id", "bbox", "score"}
        assert record["category_id"] in (1, 2)
        assert 0.0 <= record["score"] <= 1.0


def test_batching_does_not_change_the_result(split):
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    one = predict_split(_StubModel(boxes, labels), split["dataset"], img_size=128, batch_size=1)
    two = predict_split(_StubModel(boxes, labels), split["dataset"], img_size=128, batch_size=2)
    assert len(one) == len(two)
    assert sorted(r["category_id"] for r in one) == sorted(r["category_id"] for r in two)


def test_model_is_left_in_the_training_mode_it_arrived_in(split):
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    model = _StubModel(boxes, labels)
    model.train()
    predict_split(model, split["dataset"], img_size=128)
    assert model.training is True


def test_empty_dataset_raises_rather_than_scoring_nothing():
    with pytest.raises(EvaluationError, match="no items"):
        predict_split(_StubModel([], []), _StubDataset([], {1: 0}))


def test_missing_class_map_raises():
    dataset = _StubDataset([(1, "x.jpg", 10, 10)], catid_to_idx={})
    with pytest.raises(EvaluationError, match="no class map"):
        predict_split(_StubModel([[]], [[]]), dataset)


def test_summarize_flags_a_nonstandard_maxdets(split):
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    result, _detections, protocol = evaluate_split(
        model=_StubModel(boxes, labels),
        dataset=split["dataset"],
        ann_file=split["ann_file"],
        img_size=128,
        max_detections=300,
    )
    report = summarize(result, protocol)
    assert report["protocol"]["is_standard_maxdets"] is False
    assert "not comparable" in report["warning"]
    # pycocotools computes the primary AP at maxDets=100 only; anything else
    # returns its -1.0 sentinel. The report must not present that as a score.
    assert report["ap"] == pytest.approx(-1.0)


def test_summarize_is_json_serializable(split):
    boxes, labels = _letterbox_boxes(split["coco"], 128)
    result, _detections, protocol = evaluate_split(
        _StubModel(boxes, labels), split["dataset"], split["ann_file"], img_size=128
    )
    report = summarize(result, protocol)
    json.dumps(report)
    assert report["protocol"]["postprocessor"]
    assert report["num_images"] == 2
