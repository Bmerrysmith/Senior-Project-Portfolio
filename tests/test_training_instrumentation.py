"""CPU-only tests for the training-run instrumentation.

Everything here exists to answer questions the 2026-07-30 run could not answer
after the fact:

* it clipped 3150 of 3150 optimizer steps at ``grad_clip=0.5`` and the log kept
  only that count, so the *distribution* being clipped -- the number needed to
  choose a real threshold, or to drop clipping -- was gone;
* its loss fell for 14 epochs while eval-mode AP came out 0.0000, and nothing
  recorded how much of the classification loss was the positive term versus the
  background term;
* the eval/train BatchNorm gap (0.9367 peak confidence under batch statistics
  against ~0.02 under running statistics) was only discovered by re-running the
  checkpoint afterwards.

The binding requirement is that observing a run must not change it. The parity
probe runs the model in train mode, which updates BN running statistics, so it
snapshots and restores every buffer; the tests below check that directly rather
than trusting the ordering of a ``finally`` block.
"""

import json

import pytest
import torch
from test_weeddet_train import _write_synthetic_split  # noqa: F401  (shared fixture builder)

from agrinav.models import weeddet_v6b as wd
from agrinav.training.weeddet_train import _CocoSplitDataset

pytestmark = pytest.mark.unit

CLASS_NAMES = ("rice_protect", "weed_target", "non_target_aquatic")


def _dataset(tmp_path):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    return _CocoSplitDataset(ann_file, images_root, CLASS_NAMES, img_size=64, augment=False)


def _config(tmp_path, dataset, **overrides):
    config = {
        "device": "cpu",
        "seed": 42,
        "num_classes": 3,
        "class_names": list(CLASS_NAMES),
        "img_size": 64,
        "batch_size": 2,
        "num_workers": 0,
        "num_epochs": 1,
        "save_every": 99,
        "repeat_factor": 1,
        "base_lr": 1e-4,
        "use_amp": False,
        "use_ema": False,
        "pretrained_backbone": False,
        "checkpoint_dir": str(tmp_path / "ckpt"),
        "train_dataset": dataset,
        "no_progress": True,
    }
    config.update(overrides)
    return config


def _rows(tmp_path):
    text = (tmp_path / "ckpt" / "metrics.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _batch(dataset, n=2):
    return torch.stack([dataset[i][0] for i in range(min(n, len(dataset)))])


# --------------------------------------------------------------------------- #
# gradient norms
# --------------------------------------------------------------------------- #
def test_grad_norm_quantiles_are_recorded_per_epoch(tmp_path):
    """`clipped_steps` alone cannot say what threshold would have been right."""
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))
    for row in _rows(tmp_path):
        assert row["grad_norm/p50"] > 0
        assert row["grad_norm/min"] <= row["grad_norm/p50"] <= row["grad_norm/max"]
        assert row["grad_norm/p50"] <= row["grad_norm/p90"] <= row["grad_norm/p99"]
        assert row["grad_norm/clip_threshold"] == 0.5
        assert 0.0 <= row["grad_norm/clipped_fraction"] <= 1.0


def test_recorded_norms_are_pre_clip(tmp_path):
    """torch returns the norm BEFORE clipping; a post-clip number would be
    capped at the threshold and useless for choosing one."""
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset, grad_clip=1e-6))
    row = _rows(tmp_path)[-1]
    assert row["grad_norm/max"] > 1e-6, "norms look clipped -- they must be pre-clip"
    assert row["grad_norm/clipped_fraction"] == pytest.approx(1.0)


def test_clipped_fraction_agrees_with_clipped_steps(tmp_path):
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset, grad_clip=1e-6))
    row = _rows(tmp_path)[-1]
    assert row["clipped_steps"] == row["n_batches"]


def test_grad_norm_dump_is_off_by_default_and_writable(tmp_path):
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset))
    assert not list((tmp_path / "ckpt").glob("grad_norms_epoch*.json"))

    other = tmp_path / "dump"
    other.mkdir()
    wd.train_with_progress(
        _config(other, _dataset(other), dump_grad_norms=True),
    )
    dumps = sorted((other / "ckpt").glob("grad_norms_epoch*.json"))
    assert len(dumps) == 1
    norms = json.loads(dumps[0].read_text(encoding="utf-8"))
    assert norms and all(isinstance(v, float) for v in norms)


# --------------------------------------------------------------------------- #
# positive vs negative classification loss
# --------------------------------------------------------------------------- #
def test_cls_loss_splits_exactly_into_positive_and_negative(tmp_path):
    """The halves must reconstruct the whole, or the split means nothing."""
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    model.train()
    images = _batch(dataset)
    targets = [dataset[i][1] for i in range(min(2, len(dataset)))]
    losses = model(images, targets)
    assert float(losses["cls_loss_pos"]) + float(losses["cls_loss_neg"]) == pytest.approx(
        float(losses["cls_loss"].detach()), rel=1e-5
    )


def test_the_split_is_detached_from_the_graph():
    """A diagnostic that carried gradient would be a training change."""
    loss = wd.HardTargetFocalLikeLoss()
    pred = torch.randn(64, 1, requires_grad=True)
    target = torch.zeros(64, 1)
    target[:4] = 1.0
    total, pos, neg = loss(pred, target, return_split=True)
    assert total.requires_grad
    assert not pos.requires_grad and not neg.requires_grad
    assert float(pos) + float(neg) == pytest.approx(float(total.detach()), rel=1e-6)


def test_return_split_does_not_change_the_total():
    """Both paths read the same weighted tensor, so the objective is unchanged."""
    loss = wd.HardTargetFocalLikeLoss()
    torch.manual_seed(0)
    pred = torch.randn(128, 2)
    target = torch.zeros(128, 2)
    target[:5, 0] = 1.0
    plain = loss(pred, target)
    split_total, _, _ = loss(pred, target, return_split=True)
    assert float(plain) == float(split_total)


def test_split_reaches_metrics_jsonl(tmp_path):
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset))
    row = _rows(tmp_path)[-1]
    assert "train/cls_loss_pos" in row
    assert "train/cls_loss_neg" in row
    assert "train/num_pos_anchors" in row
    assert row["train/cls_loss_pos"] + row["train/cls_loss_neg"] == pytest.approx(
        row["train/cls_loss"], rel=1e-5
    )


def test_diagnostics_are_not_added_to_the_objective(tmp_path):
    """The dict grew; the trained quantity must not.

    `losses.get('total_loss', sum(losses.values()))` would have silently folded
    every diagnostic into the backward pass had 'total_loss' ever gone missing.
    """
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    model.train()
    losses = model(_batch(dataset), [dataset[i][1] for i in range(min(2, len(dataset)))])
    assert float(losses["total_loss"].detach()) == pytest.approx(
        float(losses["cls_loss"].detach()) + float(losses["reg_loss"].detach()), rel=1e-5
    )


# --------------------------------------------------------------------------- #
# train/eval BatchNorm parity probe
# --------------------------------------------------------------------------- #
def test_parity_probe_reports_both_modes(tmp_path):
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    report = wd.train_eval_confidence_parity(model, _batch(dataset))
    assert 0.0 <= report["parity/eval_max_conf"] <= 1.0
    assert 0.0 <= report["parity/train_max_conf"] <= 1.0
    assert report["parity/max_conf_gap"] == pytest.approx(
        report["parity/train_max_conf"] - report["parity/eval_max_conf"]
    )
    assert report["parity/max_conf_ratio"] > 0


def test_parity_probe_does_not_move_bn_running_statistics(tmp_path):
    """The probe forwards in train mode, which updates BN buffers. It must undo that.

    Without the snapshot/restore this "observation" would inject the probe images
    into every running statistic, once per epoch, for the whole run.
    """
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    model.train()
    before = {
        name: (m.running_mean.clone(), m.running_var.clone(), int(m.num_batches_tracked))
        for name, m in model.named_modules()
        if isinstance(m, torch.nn.BatchNorm2d)
    }
    wd.train_eval_confidence_parity(model, _batch(dataset))
    for name, m in model.named_modules():
        if not isinstance(m, torch.nn.BatchNorm2d):
            continue
        mean, var, tracked = before[name]
        assert torch.equal(m.running_mean, mean), f"{name} running_mean moved"
        assert torch.equal(m.running_var, var), f"{name} running_var moved"
        assert int(m.num_batches_tracked) == tracked, f"{name} num_batches_tracked moved"


def test_parity_probe_does_not_change_weights_or_grads(tmp_path):
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    model.train()
    before = {k: v.clone() for k, v in model.state_dict().items()}
    wd.train_eval_confidence_parity(model, _batch(dataset))
    after = model.state_dict()
    assert all(torch.equal(after[k], v) for k, v in before.items())
    assert all(p.grad is None for p in model.parameters())


@pytest.mark.parametrize("was_training", [True, False])
def test_parity_probe_restores_the_model_mode(tmp_path, was_training):
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    model.train(was_training)
    wd.train_eval_confidence_parity(model, _batch(dataset))
    assert model.training is was_training


def test_parity_probe_restores_the_freeze(tmp_path):
    """The probe calls model.train(), which unfreezes every BN."""
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    with torch.no_grad():
        for name, m in model.named_modules():
            if isinstance(m, torch.nn.BatchNorm2d) and name.startswith("backbone."):
                m.running_mean.fill_(0.3)
    names = wd.resolve_bn_freeze_names(model, expect_scope="backbone")
    model.train()
    wd.apply_bn_policy(model, freeze_names=names)

    wd.train_eval_confidence_parity(
        model, _batch(dataset), reapply_policy=lambda: wd.apply_bn_policy(model, freeze_names=names)
    )
    assert wd.bn_state_report(model)["bn/eval_mode"] == len(names)


def test_bn_buffer_snapshot_round_trips():
    model = wd.WeedDet(num_classes=2)
    snapshot = wd.bn_buffer_snapshot(model)
    assert len(snapshot) == 58
    for m in model.modules():
        if isinstance(m, torch.nn.BatchNorm2d):
            with torch.no_grad():
                m.running_mean.fill_(9.0)
    assert wd.bn_buffer_restore(model, snapshot) == 58
    for m in model.modules():
        if isinstance(m, torch.nn.BatchNorm2d):
            assert torch.equal(m.running_mean, torch.zeros_like(m.running_mean))


def test_parity_lands_in_metrics_jsonl(tmp_path):
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset, parity_probe_images=2))
    row = _rows(tmp_path)[-1]
    assert row["parity/images"] == 2
    assert "parity/max_conf_ratio" in row
    assert "parity/train_max_conf" in row


def test_parity_probe_can_be_disabled(tmp_path):
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset, parity_probe_images=0))
    assert not any(k.startswith("parity/") for k in _rows(tmp_path)[-1])


def test_a_failing_probe_does_not_take_the_run_down(tmp_path, monkeypatch):
    """Diagnostics are not allowed to cost a training run."""
    dataset = _dataset(tmp_path)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(wd, "train_eval_confidence_parity", _boom)
    wd.train_with_progress(_config(tmp_path, dataset))
    rows = _rows(tmp_path)
    assert len(rows) == 1
    assert not any(k.startswith("parity/") for k in rows[0])
