"""CPU-only tests for the ``--overfit`` gate.

The gate used to be ``final_epoch_loss < first_epoch_loss``. That condition is
satisfied by any model whose optimiser is wired up at all, and it passed for the
2026-07-28 checkpoints, whose loss fell over 14 epochs and which then scored
AP 0.0000 / AP50 0.0001 in eval mode. The classification head had learned --
0.9367 peak confidence when forced to use batch statistics -- but the BatchNorm
running statistics it was evaluated with had not, and a gate that never decodes a
box and never runs the eval-mode path cannot see that.

The gate now runs the real postprocessor through the real COCO evaluator on the
eval path, and additionally compares train-mode against eval-mode confidence on
the same images. Its thresholds are provisional (see the ``--overfit-min-*``
help text); these tests pin the *logic*, not the numbers, so re-setting a
threshold from pilot evidence does not require rewriting them.
"""

import json

import pytest
import torch
from test_weeddet_train import _write_synthetic_split  # noqa: F401  (shared fixture builder)

from agrinav.training import weeddet_train as wt
from agrinav.training.weeddet_train import _CocoSplitDataset, _subset_coco_gt, main

pytestmark = pytest.mark.unit

CLASS_NAMES = "rice_protect,weed_target,non_target_aquatic"


class _FakeResult:
    """Stands in for a ``CocoEvalResult``; only the gated fields are read."""

    def __init__(self, ap50, ar_100, ap=0.3):
        self.ap = ap
        self.ap50 = ap50
        self.ar_100 = ar_100
        self.num_detections = 7
        self.num_gt_annotations = 3


def _argv(tmp_path, ann_file, images_root, **extra):
    argv = [
        "--overfit",
        "2",
        "--ann-file",
        ann_file,
        "--images-root",
        images_root,
        "--class-names",
        CLASS_NAMES,
        "--img-size",
        "64",
        "--batch-size",
        "2",
        "--epochs",
        "2",
        "--device",
        "cpu",
        "--checkpoint-dir",
        str(tmp_path / "ckpt"),
    ]
    for key, value in extra.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    return argv


# --------------------------------------------------------------------------- #
# the subset ground truth
# --------------------------------------------------------------------------- #
def test_subset_gt_covers_only_the_images_the_dataset_kept(tmp_path):
    """Scoring N memorised images against the full split measures the split.

    ``_CocoSplitDataset(limit=N)`` truncates its image list but the annotation
    file on disk still describes everything; every unscored image would count as
    a miss and recall would report N/total instead of the model's recall.
    """
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    full = _CocoSplitDataset(ann_file, images_root, tuple(CLASS_NAMES.split(",")), img_size=64)
    limited = _CocoSplitDataset(
        ann_file, images_root, tuple(CLASS_NAMES.split(",")), img_size=64, limit=1
    )

    assert len(_subset_coco_gt(full)["images"]) == 2
    assert len(_subset_coco_gt(full)["annotations"]) == 3

    subset = _subset_coco_gt(limited)
    assert [image["id"] for image in subset["images"]] == [10]
    assert {ann["image_id"] for ann in subset["annotations"]} == {10}
    assert len(subset["annotations"]) == 2


def test_subset_gt_keeps_the_source_categories(tmp_path):
    """Category ids must survive verbatim or pycocotools rejects the detections."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    dataset = _CocoSplitDataset(ann_file, images_root, tuple(CLASS_NAMES.split(",")), img_size=64)
    with open(ann_file, encoding="utf-8") as handle:
        source = json.load(handle)
    assert _subset_coco_gt(dataset)["categories"] == source["categories"]


# --------------------------------------------------------------------------- #
# the gate decides on decoded detections
# --------------------------------------------------------------------------- #
def test_two_epochs_fail_the_gate_on_decoded_metrics_not_on_the_loss(tmp_path, capsys):
    """A model that has not memorised anything must fail, and say why.

    Two epochs is nowhere near memorisation, so this exercises the real decode
    and the real evaluator end to end.
    """
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    assert main(_argv(tmp_path, ann_file, images_root)) == 1
    out = capsys.readouterr().out
    assert "[overfit] decoded: AP=" in out
    assert "[overfit] bn parity:" in out
    assert "FAILED" in out
    assert "AP50" in out.split("FAILED")[1]


def test_the_gate_passes_when_the_decoded_metrics_are_good(tmp_path, monkeypatch, capsys):
    """Threshold logic in isolation: real memorisation is too slow for CI.

    The model, the decode and the parity probe all still run; only the scoring is
    substituted, so a change to how the gate combines its conditions is caught
    here without depending on 60 epochs of CPU training.
    """
    monkeypatch.setattr(
        wt, "_subset_coco_gt", lambda dataset: {"images": [], "annotations": [], "categories": []}
    )
    monkeypatch.setattr(
        "agrinav.evaluation.metrics.evaluate_coco_detections",
        lambda *a, **k: _FakeResult(ap50=0.82, ar_100=0.77),
    )
    monkeypatch.setattr(
        wt._WD,
        "train_eval_confidence_parity",
        lambda *a, **k: {
            "parity/train_max_conf": 0.90,
            "parity/eval_max_conf": 0.85,
            "parity/max_conf_ratio": 0.90 / 0.85,
        },
    )
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    assert main(_argv(tmp_path, ann_file, images_root)) == 0
    assert "PASSED" in capsys.readouterr().out


def test_a_bn_mode_gap_fails_the_gate_even_with_good_ap(tmp_path, monkeypatch, capsys):
    """The 2026-07-28 shape exactly: high train-mode confidence, dead in eval mode.

    AP is passed as healthy here so the only thing that can fail is the parity
    condition -- which is the condition the old gate did not have.
    """
    monkeypatch.setattr(
        wt, "_subset_coco_gt", lambda dataset: {"images": [], "annotations": [], "categories": []}
    )
    monkeypatch.setattr(
        "agrinav.evaluation.metrics.evaluate_coco_detections",
        lambda *a, **k: _FakeResult(ap50=0.82, ar_100=0.77),
    )
    monkeypatch.setattr(
        wt._WD,
        "train_eval_confidence_parity",
        lambda *a, **k: {
            "parity/train_max_conf": 0.9367,
            "parity/eval_max_conf": 0.0200,
            "parity/max_conf_ratio": 0.9367 / 0.0200,
        },
    )
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    assert main(_argv(tmp_path, ann_file, images_root)) == 1
    out = capsys.readouterr().out
    assert "confidence ratio" in out
    assert "AP50" not in out.split("FAILED")[1], "AP was healthy; only parity should fail"


def test_thresholds_are_configurable(tmp_path, monkeypatch):
    """Provisional numbers must be overridable without editing source."""
    monkeypatch.setattr(
        wt, "_subset_coco_gt", lambda dataset: {"images": [], "annotations": [], "categories": []}
    )
    monkeypatch.setattr(
        "agrinav.evaluation.metrics.evaluate_coco_detections",
        lambda *a, **k: _FakeResult(ap50=0.11, ar_100=0.09),
    )
    monkeypatch.setattr(
        wt._WD,
        "train_eval_confidence_parity",
        lambda *a, **k: {
            "parity/train_max_conf": 0.5,
            "parity/eval_max_conf": 0.5,
            "parity/max_conf_ratio": 1.0,
        },
    )
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    assert main(_argv(tmp_path, ann_file, images_root)) == 1
    assert (
        main(
            _argv(
                tmp_path,
                ann_file,
                images_root,
                overfit_min_ap50=0.10,
                overfit_min_recall=0.05,
            )
        )
        == 0
    )


def test_the_gate_reports_the_gradient_norm_distribution(tmp_path, capsys):
    """Choosing a real grad_clip needs the distribution, not a clipped count."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    main(_argv(tmp_path, ann_file, images_root))
    out = capsys.readouterr().out
    assert "[overfit] grad_norm p50=" in out
    assert "clipped" in out


def test_the_gate_reports_the_positive_negative_loss_split(tmp_path, capsys):
    """ "Loss went down" can mean "it learned to predict background everywhere"."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    main(_argv(tmp_path, ann_file, images_root))
    out = capsys.readouterr().out
    assert "cls_pos=" in out and "cls_neg=" in out


def test_overfit_leaves_bn_state_visible(tmp_path, capsys):
    """The frozen-layer count belongs in the log of every run, not just training."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    main(_argv(tmp_path, ann_file, images_root))
    assert "[overfit] bn frozen=" in capsys.readouterr().out


def test_cpu_run_freezes_nothing_and_that_is_correct(tmp_path):
    """No CUDA means no ImageNet load, so there are no pretrained statistics."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    model = wt._WD.WeedDet(num_classes=3)
    assert wt._WD.resolve_bn_freeze_names(model, pretrained_loaded=False) == frozenset()
    assert wt._WD.apply_bn_policy(model, freeze_names=frozenset()) == (0, 58)
    assert torch.cuda.is_available() or True  # documents the precondition
