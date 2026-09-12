"""Tests for the torchvision baseline control.

The baseline exists so a WeedDet AP has something to be measured against, which
makes *comparability* the property under test, not accuracy. Three things decide
it and each is pinned here:

* the reference model sees WeedDet's exact tensor (no second resize, no second
  normalisation);
* the label shift into and back out of torchvision's background-at-0 convention
  round-trips;
* the emitted ``protocol`` uses the same keys as the WeedDet evaluator's, so two
  reports can be diffed rather than eyeballed.

The decisive test drives the whole scoring chain with a stub whose predictions
are exactly the ground truth and asserts AP 1.0 -- an error in the label shift,
the letterbox inverse, or the category map moves that number.
"""

from __future__ import annotations

import json

import pytest
import torch
from PIL import Image

from agrinav.training.baseline_det_control import (
    SUPPORTED_ARCHS,
    BaselineConfig,
    BaselineError,
    build_config,
    build_model,
    evaluate_split,
    predict_split,
    to_torchvision_targets,
    train,
)

pytestmark = pytest.mark.unit


class _StubDataset:
    """Minimal stand-in for ``_CocoSplitDataset``: items() plus a class map."""

    def __init__(self, records, catid_to_idx):
        self._records = records
        self.catid_to_idx = catid_to_idx

    def items(self):
        return list(self._records)

    def __len__(self):
        return len(self._records)


class _StubTorchvisionModel(torch.nn.Module):
    """Returns fixed boxes in torchvision's output shape and label convention.

    A real torchvision detector emits ``[{boxes, scores, labels}]`` with labels
    1-based over a background at 0, already suppressed and already mapped back to
    the input size. The stub reproduces exactly that contract so the code under
    test is the adapter, not the detector.
    """

    def __init__(self, boxes_per_image, labels_per_image, score=0.99):
        super().__init__()
        self.boxes_per_image = boxes_per_image
        self.labels_per_image = labels_per_image
        self.score = score
        self.calls = 0

    def forward(self, images, targets=None):
        start = self.calls
        self.calls += len(images)
        outputs = []
        for offset in range(len(images)):
            boxes = torch.tensor(self.boxes_per_image[start + offset], dtype=torch.float32).reshape(
                -1, 4
            )
            labels = torch.tensor(self.labels_per_image[start + offset], dtype=torch.int64)
            outputs.append(
                {
                    "boxes": boxes,
                    "scores": torch.full((len(boxes),), self.score),
                    "labels": labels,
                }
            )
        return outputs


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
        Image.new("RGB", (width, height), (30 + index * 40, 90, 30)).save(images_root / name)
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


def _letterbox_gt(coco, image_size):
    """GT boxes in letterboxed space with torchvision's 1-based labels."""
    from agrinav.models.weeddet_v6b import letterbox_pil

    boxes_per_image, labels_per_image = [], []
    for record in coco["images"]:
        _canvas, scale_x, scale_y, pad_left, pad_top = letterbox_pil(
            Image.new("RGB", (record["width"], record["height"])), image_size
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
            # contiguous index (category_id - 1) shifted into torchvision's
            # foreground range [1, N] -- the convention the adapter must undo.
            labels.append(ann["category_id"])
        boxes_per_image.append(boxes)
        labels_per_image.append(labels)
    return boxes_per_image, labels_per_image


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
    return {
        "ann_file": ann_file,
        "dataset": _StubDataset(records, catid_to_idx={1: 0, 2: 1}),
        "coco": coco,
    }


# --------------------------------------------------------------------------- #
# the decisive test: perfect predictions must score AP 1.0 through this adapter
# --------------------------------------------------------------------------- #
def test_perfect_predictions_score_ap_one(split):
    config = BaselineConfig(img_size=256, eval_batch_size=2)
    boxes, labels = _letterbox_gt(split["coco"], config.img_size)
    model = _StubTorchvisionModel(boxes, labels)

    result, detections, protocol = evaluate_split(
        model, split["dataset"], split["ann_file"], config, device="cpu"
    )

    assert len(detections) == len(split["coco"]["annotations"])
    assert result.ap == pytest.approx(1.0, abs=1e-6)
    assert result.ap50 == pytest.approx(1.0, abs=1e-6)
    assert protocol["images"] == 2


def test_shifted_boxes_do_not_score_ap_one(split):
    """A 25 px error must move the number; otherwise the geometry is untested."""
    config = BaselineConfig(img_size=256, eval_batch_size=2)
    boxes, labels = _letterbox_gt(split["coco"], config.img_size)
    shifted = [[[x0 + 25, y0 + 25, x1 + 25, y1 + 25] for x0, y0, x1, y1 in per] for per in boxes]

    result, _detections, _protocol = evaluate_split(
        _StubTorchvisionModel(shifted, labels), split["dataset"], split["ann_file"], config
    )
    assert result.ap < 0.9


def test_forgetting_the_label_shift_destroys_ap(split):
    """Emitting 0-based labels straight through must not accidentally still score.

    This is the failure mode the +1/-1 convention exists to prevent: it swaps
    ``rice_protect`` and ``weed_target`` and drops one class off the end.
    """
    config = BaselineConfig(img_size=256, eval_batch_size=2)
    boxes, labels = _letterbox_gt(split["coco"], config.img_size)
    unshifted = [[label - 1 for label in per] for per in labels]

    result, _detections, _protocol = evaluate_split(
        _StubTorchvisionModel(boxes, unshifted), split["dataset"], split["ann_file"], config
    )
    assert result.ap < 1.0


def test_background_labels_are_dropped_not_mapped(split):
    """Label 0 is torchvision's background; it must never become a category id."""
    config = BaselineConfig(img_size=256, eval_batch_size=2)
    boxes, labels = _letterbox_gt(split["coco"], config.img_size)
    with_background = [[0] * len(per) for per in labels]

    detections = predict_split(
        _StubTorchvisionModel(boxes, with_background), split["dataset"], config
    )
    assert detections == []


class _SilentWeedDet(torch.nn.Module):
    """A WeedDet-shaped model that predicts nothing.

    The protocol dict is built from the configuration, not the predictions, so an
    empty detector is enough to compare the two evaluators' report shapes.
    """

    num_classes = 2

    def _get_logits(self, images):
        batch, height, width = images.shape[0], *images.shape[-2:]
        cls = torch.full((batch, self.num_classes, 1, 1), -20.0)
        return [cls], [torch.zeros(batch, 4, 1, 1)], torch.zeros(1, 4), (height, width)


def test_protocol_keys_match_the_weeddet_evaluator(split):
    """Two reports must be diffable. A renamed key on either side silently ends that.

    Compared against the real WeedDet evaluator rather than a hand-copied list,
    so the assertion cannot drift out of date without failing.
    """
    from agrinav.evaluation.runner import evaluate_split as weeddet_evaluate_split

    config = BaselineConfig(img_size=256, eval_batch_size=2)
    boxes, labels = _letterbox_gt(split["coco"], config.img_size)

    _result, _detections, baseline_protocol = evaluate_split(
        _StubTorchvisionModel(boxes, labels), split["dataset"], split["ann_file"], config
    )
    _wd_result, _wd_detections, weeddet_protocol = weeddet_evaluate_split(
        _SilentWeedDet(), split["dataset"], split["ann_file"], img_size=config.img_size
    )

    extra = set(baseline_protocol) - set(weeddet_protocol)
    missing = set(weeddet_protocol) - set(baseline_protocol)
    assert not missing, f"baseline report is missing WeedDet protocol keys: {sorted(missing)}"
    # The one added field names the difference that cannot be removed.
    assert extra == {"suppression"}
    assert "hard NMS" in baseline_protocol["suppression"]
    assert baseline_protocol["use_soft_nms"] is False
    assert weeddet_protocol["use_soft_nms"] is True


# --------------------------------------------------------------------------- #
# target conversion
# --------------------------------------------------------------------------- #
def test_targets_shift_labels_into_the_foreground_range():
    targets = [{"boxes": torch.tensor([[1.0, 2.0, 5.0, 6.0]]), "labels": torch.tensor([0])}]
    converted = to_torchvision_targets(targets)
    assert converted[0]["labels"].tolist() == [1]
    assert converted[0]["boxes"].tolist() == [[1.0, 2.0, 5.0, 6.0]]


def test_targets_drop_degenerate_boxes():
    """torchvision raises on a zero-area box; a crash mid-epoch is the worse failure."""
    targets = [
        {
            "boxes": torch.tensor([[1.0, 2.0, 5.0, 6.0], [3.0, 3.0, 3.0, 9.0]]),
            "labels": torch.tensor([0, 1]),
        }
    ]
    converted = to_torchvision_targets(targets)
    assert len(converted[0]["boxes"]) == 1
    assert converted[0]["labels"].tolist() == [1]


def test_targets_keep_empty_images_with_the_right_shapes():
    targets = [{"boxes": torch.zeros((0, 4)), "labels": torch.zeros((0,), dtype=torch.int64)}]
    converted = to_torchvision_targets(targets)
    assert converted[0]["boxes"].shape == (0, 4)
    assert converted[0]["labels"].shape == (0,)
    assert converted[0]["labels"].dtype == torch.int64


# --------------------------------------------------------------------------- #
# model construction: the comparability guarantees
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("arch", SUPPORTED_ARCHS)
def test_internal_transform_is_neutralised(arch):
    """The reference must see WeedDet's tensor: no second resize, no second norm."""
    config = BaselineConfig(arch=arch, init="scratch", img_size=512)
    model = build_model(config)
    transform = model.transform
    assert list(transform.image_mean) == [0.0, 0.0, 0.0]
    assert list(transform.image_std) == [1.0, 1.0, 1.0]
    assert max(transform.min_size) == transform.max_size == config.img_size


@pytest.mark.parametrize("arch", SUPPORTED_ARCHS)
def test_head_is_rebuilt_for_our_class_count(arch):
    """Foreground classes plus torchvision's background slot, and no more."""
    config = BaselineConfig(arch=arch, init="scratch", class_names=("rice_protect", "weed_target"))
    model = build_model(config)
    if arch.startswith("fasterrcnn"):
        assert model.roi_heads.box_predictor.cls_score.out_features == 3
    else:
        assert model.head.classification_head.num_classes == 3


@pytest.mark.parametrize("arch", SUPPORTED_ARCHS)
def test_suppression_knobs_match_the_configured_protocol(arch):
    """A baseline scored at a different NMS is not a baseline for this number."""
    config = BaselineConfig(arch=arch, init="scratch", nms_iou=0.37, max_detections=42)
    model = build_model(config)
    if arch.startswith("fasterrcnn"):
        assert model.roi_heads.nms_thresh == pytest.approx(0.37)
        assert model.roi_heads.detections_per_img == 42
    else:
        assert model.nms_thresh == pytest.approx(0.37)
        assert model.detections_per_img == 42


# --------------------------------------------------------------------------- #
# configuration: fail closed rather than produce an uninterpretable number
# --------------------------------------------------------------------------- #
def test_validate_rejects_an_unknown_arch():
    with pytest.raises(BaselineError, match="unknown --arch"):
        BaselineConfig(arch="yolov99").validate()


def test_validate_rejects_an_unknown_init():
    with pytest.raises(BaselineError, match="unknown --init"):
        BaselineConfig(init="magic").validate()


def test_validate_rejects_an_img_size_torchvision_would_pad():
    """512 is fine, 500 is not: the pad would enlarge the canvas silently."""
    with pytest.raises(BaselineError, match="multiple of 32"):
        BaselineConfig(img_size=500).validate()


def test_validate_rejects_empty_class_names():
    with pytest.raises(BaselineError, match="class_names is empty"):
        BaselineConfig(class_names=()).validate()


def test_build_config_rejects_unknown_yaml_keys(tmp_path):
    """A silently ignored key is how a run stops being the run its config describes."""
    import argparse

    config_path = tmp_path / "bad.yaml"
    config_path.write_text("arch: fcos_resnet50_fpn\nlearning_rate: 0.1\n", encoding="utf-8")
    args = argparse.Namespace(
        config=str(config_path), class_names=None, no_augment=False, no_amp=False
    )
    with pytest.raises(BaselineError, match="unknown keys"):
        build_config(args)


def test_build_config_lets_cli_flags_win_over_the_file(tmp_path):
    import argparse

    config_path = tmp_path / "ok.yaml"
    config_path.write_text("arch: fcos_resnet50_fpn\nnum_epochs: 18\n", encoding="utf-8")
    args = argparse.Namespace(
        config=str(config_path),
        class_names=None,
        no_augment=False,
        no_amp=False,
        num_epochs=3,
        arch="retinanet_resnet50_fpn_v2",
    )
    config = build_config(args)
    assert config.num_epochs == 3
    assert config.arch == "retinanet_resnet50_fpn_v2"


def test_shipped_baseline_config_loads_and_validates():
    """The config in version control must actually be loadable, not aspirational."""
    import argparse
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1] / "configs" / "training" / "baseline_det_control.yaml"
    )
    args = argparse.Namespace(config=str(path), class_names=None, no_augment=False, no_amp=False)
    config = build_config(args)
    assert config.class_names == ("rice_protect", "weed_target")
    assert config.max_detections == 100  # COCO standard, or the AP is not comparable
    assert config.img_size == 512


def test_shipped_config_protocol_matches_the_weeddet_defaults():
    """The two arms must share every knob that decides whether the APs are the same quantity."""
    import argparse
    from pathlib import Path

    from agrinav.inference.postprocess import (
        DEFAULT_MAX_DETECTIONS,
        DEFAULT_NMS_IOU,
        DEFAULT_SCORE_THRESHOLD,
    )

    path = (
        Path(__file__).resolve().parents[1] / "configs" / "training" / "baseline_det_control.yaml"
    )
    args = argparse.Namespace(config=str(path), class_names=None, no_augment=False, no_amp=False)
    config = build_config(args)
    assert config.score_threshold == pytest.approx(DEFAULT_SCORE_THRESHOLD)
    assert config.nms_iou == pytest.approx(DEFAULT_NMS_IOU)
    assert config.max_detections == DEFAULT_MAX_DETECTIONS


def test_the_two_arms_agree_on_image_size_and_epochs():
    """A baseline trained on a different budget is a different experiment."""
    from pathlib import Path

    import yaml

    configs = Path(__file__).resolve().parents[1] / "configs" / "training"
    baseline = yaml.safe_load((configs / "baseline_det_control.yaml").read_text(encoding="utf-8"))
    weeddet = yaml.safe_load((configs / "detector_rice_phase2.yaml").read_text(encoding="utf-8"))
    for key in ("img_size", "num_epochs", "seed", "class_names", "val_ap_interval"):
        assert baseline[key] == weeddet[key], f"{key} differs between the two arms"


# --------------------------------------------------------------------------- #
# training loop behaviour
# --------------------------------------------------------------------------- #
class _LossModel(torch.nn.Module):
    """Emits a configurable loss in train mode and fixed detections in eval mode."""

    def __init__(self, loss_value=1.0):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.zeros(1))
        self.loss_value = loss_value

    def forward(self, images, targets=None):
        if self.training:
            return {"loss_classifier": self.weight.sum() + self.loss_value}
        return [
            {
                "boxes": torch.zeros((0, 4)),
                "scores": torch.zeros((0,)),
                "labels": torch.zeros((0,), dtype=torch.int64),
            }
            for _ in images
        ]


class _TensorDataset(torch.utils.data.Dataset):
    """Yields the ``(tensor, target)`` pairs ``collate_fn`` expects."""

    def __init__(self, count, img_size):
        self.count = count
        self.img_size = img_size

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        return torch.zeros(3, self.img_size, self.img_size), {
            "boxes": torch.tensor([[1.0, 1.0, 10.0, 10.0]]),
            "labels": torch.tensor([0]),
            "orig_h": self.img_size,
            "orig_w": self.img_size,
        }


def test_non_finite_loss_raises_rather_than_writing_a_checkpoint(tmp_path):
    config = BaselineConfig(
        img_size=64, batch_size=2, num_workers=0, num_epochs=1, use_amp=False, val_ap_interval=0
    )
    with pytest.raises(BaselineError, match="non-finite loss"):
        train(
            config,
            _TensorDataset(4, config.img_size),
            out_dir=str(tmp_path / "run"),
            model=_LossModel(loss_value=float("nan")),
        )
    assert not (tmp_path / "run" / "baseline_last.pth").exists()


def test_a_run_without_validation_is_recorded_as_not_a_baseline(tmp_path):
    config = BaselineConfig(
        img_size=64, batch_size=2, num_workers=0, num_epochs=1, use_amp=False, val_ap_interval=0
    )
    run = train(
        config,
        _TensorDataset(4, config.img_size),
        out_dir=str(tmp_path / "run"),
        model=_LossModel(),
    )
    assert run["best_epoch"] is None
    assert "plumbing check, not a baseline" in run["warning"]
    assert run["selection_metric"].startswith("none")


def test_val_dataset_without_ann_file_is_rejected(tmp_path):
    config = BaselineConfig(img_size=64, num_workers=0, num_epochs=1, use_amp=False)
    with pytest.raises(BaselineError, match="must be given together"):
        train(
            config,
            _TensorDataset(2, config.img_size),
            val_dataset=_TensorDataset(2, config.img_size),
            val_ann_file=None,
            out_dir=str(tmp_path / "run"),
            model=_LossModel(),
        )


def test_run_record_is_written_and_self_describing(tmp_path):
    config = BaselineConfig(
        img_size=64, batch_size=2, num_workers=0, num_epochs=2, use_amp=False, val_ap_interval=0
    )
    out_dir = tmp_path / "run"
    train(config, _TensorDataset(4, config.img_size), out_dir=str(out_dir), model=_LossModel())

    record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert record["schema_version"] == "agrinav.baseline_det_control.run.v1"
    assert len(record["epochs"]) == 2
    assert record["config"]["max_detections"] == 100
    assert (out_dir / "baseline_last.pth").exists()

    checkpoint = torch.load(out_dir / "baseline_last.pth", map_location="cpu", weights_only=False)
    assert checkpoint["class_names"] == ["rice_protect", "weed_target"]
    assert checkpoint["arch"] == config.arch


def test_selection_writes_best_on_val_ap(tmp_path):
    """`best` must track the AP, not the loss, and only exist when AP was computed."""
    config = BaselineConfig(
        img_size=64, batch_size=2, num_workers=0, num_epochs=1, use_amp=False, val_ap_interval=1
    )
    ann_file, images_root, coco = _write_split(tmp_path, [("a.jpg", 64, 64, [(1, [4, 4, 20, 20])])])
    records = [(1, f"{images_root}/a.jpg", 64, 64)]
    out_dir = tmp_path / "run"

    run = train(
        config,
        _TensorDataset(2, config.img_size),
        val_dataset=_StubDataset(records, catid_to_idx={1: 0, 2: 1}),
        val_ann_file=ann_file,
        out_dir=str(out_dir),
        model=_LossModel(),
    )
    assert run["selection_metric"] == "val/AP"
    assert run["best_epoch"] == 1
    assert (out_dir / "baseline_best.pth").exists()
    assert coco["categories"][0]["name"] == "rice_protect"
