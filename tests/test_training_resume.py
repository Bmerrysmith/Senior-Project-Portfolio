"""CPU-only tests for full training-state resume.

Every epoch already wrote the optimizer, both LR schedulers and the AMP scaler
into ``weeddet_last.pth``; nothing ever read them back. A Colab VM reclaimed
mid-epoch therefore cost the entire run -- on 2026-07-30 the process was killed
at batch 224 of 225 in epoch 15 and 14 completed epochs were unusable.

The load-bearing test here is the weight-routing one: the checkpoint holds two
weight sets, ``raw_state_dict`` (the online model) and ``state_dict`` (the EMA).
Resuming the EMA weights into the online model would silently continue training
from the smoothed copy -- a different optimisation trajectory that no artifact
would reveal.
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
        "num_epochs": 2,
        "save_every": 99,
        "repeat_factor": 1,
        "base_lr": 1e-4,
        "use_amp": False,
        "use_ema": True,
        "pretrained_backbone": False,
        "checkpoint_dir": str(tmp_path / "ckpt"),
        "train_dataset": dataset,
        "no_progress": True,
    }
    config.update(overrides)
    return config


def _epochs_in(ckpt_dir):
    path = ckpt_dir / "metrics.jsonl"
    return [
        json.loads(line)["epoch"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --------------------------------------------------------------------------- #
# the load-bearing test: which weight set goes where
# --------------------------------------------------------------------------- #
def test_resume_restores_online_weights_not_the_ema_copy(tmp_path):
    """`raw_state_dict` must land in the model and `state_dict` in the EMA.

    Swapping them keeps training running and produces plausible artifacts while
    silently continuing from the smoothed weights.
    """
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, _dataset(tmp_path)))
    saved = torch.load(ckpt_dir / "weeddet_last.pth", map_location="cpu", weights_only=False)

    # EMA differs from the online model, otherwise this test proves nothing.
    key = next(k for k, v in saved["raw_state_dict"].items() if v.dtype.is_floating_point)
    assert not torch.equal(
        saved["raw_state_dict"][key], saved["state_dict"][key]
    ), "EMA and online weights are identical in this fixture; the routing test is vacuous"

    model = wd.WeedDet(num_classes=3)
    ema = wd.ModelEMA(model, decay=0.999)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4, momentum=0.9)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=10)
    warmup = wd.WarmupMultiStepLR(optimizer, warmup_iters=5, warmup_factor=0.001)

    wd._restore_training_state(
        str(ckpt_dir / "weeddet_last.pth"),
        model=model,
        ema=ema,
        optimizer=optimizer,
        lr_scheduler=scheduler,
        warmup=warmup,
        scaler=None,
        select_metric="train/total_loss",
        config={"class_names": list(CLASS_NAMES), "num_classes": 3},
        ckpt_dir=str(ckpt_dir),
        log=lambda *_a: None,
    )

    assert torch.equal(model.state_dict()[key], saved["raw_state_dict"][key])
    assert torch.equal(ema.ema.state_dict()[key], saved["state_dict"][key])


# --------------------------------------------------------------------------- #
# continuation
# --------------------------------------------------------------------------- #
def test_resume_continues_at_the_next_epoch(tmp_path):
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))
    assert _epochs_in(ckpt_dir) == [1, 2]

    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=4, resume="auto"))
    # 3 and 4 only: a resumed run must not redo epochs already paid for.
    assert _epochs_in(ckpt_dir) == [1, 2, 3, 4]

    status = json.loads((ckpt_dir / "status.json").read_text(encoding="utf-8"))
    assert status["completed"] is True
    assert status["epochs_completed"] == 4


def test_resume_restores_the_lr_schedule_rather_than_restarting_it(tmp_path):
    """Without scheduler state the LR jumps back to the top of the cosine."""
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))
    before = torch.load(ckpt_dir / "weeddet_last.pth", map_location="cpu", weights_only=False)
    step_before = before["warmup"]["iter"]
    assert step_before > 0

    model = wd.WeedDet(num_classes=3)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4, momentum=0.9)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=10)
    warmup = wd.WarmupMultiStepLR(optimizer, warmup_iters=5, warmup_factor=0.001)
    wd._restore_training_state(
        str(ckpt_dir / "weeddet_last.pth"),
        model=model,
        ema=None,
        optimizer=optimizer,
        lr_scheduler=scheduler,
        warmup=warmup,
        scaler=None,
        select_metric="train/total_loss",
        config={"class_names": list(CLASS_NAMES), "num_classes": 3},
        ckpt_dir=str(ckpt_dir),
        log=lambda *_a: None,
    )
    assert warmup.state_dict()["iter"] == step_before


def test_resume_carries_the_global_step_forward(tmp_path):
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))
    first = torch.load(ckpt_dir / "weeddet_last.pth", map_location="cpu", weights_only=False)

    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=4, resume="auto"))
    second = torch.load(ckpt_dir / "weeddet_last.pth", map_location="cpu", weights_only=False)
    assert second["global_step"] > first["global_step"]
    assert second["epoch"] == 4


# --------------------------------------------------------------------------- #
# auto mode
# --------------------------------------------------------------------------- #
def test_resume_auto_with_no_checkpoint_starts_from_epoch_one(tmp_path):
    """A first run must not fail just because it asked to resume if possible."""
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2, resume="auto"))
    assert _epochs_in(ckpt_dir) == [1, 2]


def test_resume_from_a_missing_explicit_path_is_an_error(tmp_path):
    """'auto' is permissive; a path the user typed is not."""
    dataset = _dataset(tmp_path)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        wd.train_with_progress(_config(tmp_path, dataset, resume=str(tmp_path / "nope.pth")))


# --------------------------------------------------------------------------- #
# fail closed on anything that changes what the run measures
# --------------------------------------------------------------------------- #
def test_resume_refuses_a_different_selection_metric(tmp_path):
    """`best` chosen by two different rules is not a best checkpoint."""
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))  # train-loss selection

    with pytest.raises(ValueError, match="selected checkpoints on"):
        wd.train_with_progress(
            _config(
                tmp_path,
                dataset,
                num_epochs=4,
                resume="auto",
                val_dataset=dataset,  # switches selection to val/total_loss
            )
        )
    assert (ckpt_dir / "weeddet_last.pth").exists()  # original run untouched


def test_resume_refuses_a_different_class_map(tmp_path):
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))

    model = wd.WeedDet(num_classes=3)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=10)
    warmup = wd.WarmupMultiStepLR(optimizer)
    with pytest.raises(ValueError, match="class map mismatch"):
        wd._restore_training_state(
            str(ckpt_dir / "weeddet_last.pth"),
            model=model,
            ema=None,
            optimizer=optimizer,
            lr_scheduler=scheduler,
            warmup=warmup,
            scaler=None,
            select_metric="train/total_loss",
            config={
                "class_names": ["weed_target", "rice_protect", "non_target_aquatic"],
                "num_classes": 3,
            },
            ckpt_dir=str(ckpt_dir),
            log=lambda *_a: None,
        )


def test_resume_refuses_a_different_class_count(tmp_path):
    dataset = _dataset(tmp_path)
    ckpt_dir = tmp_path / "ckpt"
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))

    model = wd.WeedDet(num_classes=3)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=10)
    warmup = wd.WarmupMultiStepLR(optimizer)
    with pytest.raises(ValueError, match="num_classes mismatch"):
        wd._restore_training_state(
            str(ckpt_dir / "weeddet_last.pth"),
            model=model,
            ema=None,
            optimizer=optimizer,
            lr_scheduler=scheduler,
            warmup=warmup,
            scaler=None,
            select_metric="train/total_loss",
            config={"class_names": list(CLASS_NAMES), "num_classes": 2},
            ckpt_dir=str(ckpt_dir),
            log=lambda *_a: None,
        )


def test_resuming_an_already_finished_run_is_an_error(tmp_path):
    """Silently doing nothing would look like a successful no-op run."""
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2))
    with pytest.raises(ValueError, match="already finished epoch"):
        wd.train_with_progress(_config(tmp_path, dataset, num_epochs=2, resume="auto"))


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #
def test_cli_exposes_resume_and_it_reaches_the_config(tmp_path):
    from agrinav.training.weeddet_train import _build_parser, build_config

    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    args = _build_parser().parse_args(
        [
            "--ann-file",
            ann_file,
            "--images-root",
            images_root,
            "--class-names",
            ",".join(CLASS_NAMES),
            "--resume",
            "auto",
            "--device",
            "cpu",
        ]
    )
    assert args.resume == "auto"
    assert build_config(args)["resume"] == "auto"


def test_resume_defaults_to_off(tmp_path):
    from agrinav.training.weeddet_train import _build_parser, build_config

    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    args = _build_parser().parse_args(
        [
            "--ann-file",
            ann_file,
            "--images-root",
            images_root,
            "--class-names",
            ",".join(CLASS_NAMES),
            "--device",
            "cpu",
        ]
    )
    assert build_config(args).get("resume") is None
