"""CPU-only tests for training run artifacts: portability, metrics, gates.

These cover the defects that made four completed A100 runs unusable:

* a checkpoint that could not be loaded off the training machine, because the
  whole live config (dataset + ``_RicesegBackboneInit``) was pickled into it and
  ``python -m`` made that class pickle as ``__main__._RicesegBackboneInit``;
* a *successful* run leaving no terminal artifact (``18 % save_every 4 == 2``),
  so completion was indistinguishable from a crash;
* a loss curve that existed only in notebook cell output Colab later truncated;
* a non-finite loss silently never updating ``best`` again.

The clean-subprocess test is the load-bearing one: the pre-existing pickle tests
round-trip in-process, where ``__main__`` is pytest, and are structurally
incapable of catching the ``__main__``-scoped pickle bug.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest
import torch
from test_weeddet_train import _write_synthetic_split  # noqa: F401  (shared fixture builder)

from agrinav.models import weeddet_v6b as wd
from agrinav.training.weeddet_train import _CocoSplitDataset, _RicesegBackboneInit


def _tiny_config(tmp_path, dataset, **overrides):
    """Smallest config that still exercises the real loop end to end on CPU."""
    config = {
        "device": "cpu",
        "seed": 42,
        "num_classes": 3,
        "class_names": list(("rice_protect", "weed_target", "non_target_aquatic")),
        "img_size": 64,
        "batch_size": 2,
        "num_workers": 0,
        "num_epochs": 2,
        "save_every": 4,  # deliberately does NOT divide num_epochs
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


def _dataset(tmp_path):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    return _CocoSplitDataset(
        ann_file,
        images_root,
        ("rice_protect", "weed_target", "non_target_aquatic"),
        img_size=64,
        augment=False,
    )


# --------------------------------------------------------------- config sanitising
def test_sanitize_config_drops_live_objects_but_keeps_provenance(tmp_path):
    dataset = _dataset(tmp_path)
    config = _tiny_config(tmp_path, dataset)
    config["backbone_init"] = _RicesegBackboneInit("/some/riceseg_backbone.pth")

    safe = wd.sanitize_config_for_save(config)

    assert "train_dataset" not in safe
    assert "backbone_init" not in safe
    # Provenance survives as plain strings.
    assert safe["train_dataset_ann_file"].endswith("train.coco.json")
    assert "/some/riceseg_backbone.pth" in safe["backbone_init_ckpt_path"]
    assert "_RicesegBackboneInit" in safe["backbone_init_repr"]
    # Scalars pass through untouched, and the result is JSON-round-trippable.
    assert safe["num_classes"] == 3
    assert json.loads(json.dumps(safe))["img_size"] == 64


def test_checkpoints_load_under_weights_only(tmp_path):
    """The strict unpickler must accept our own artifacts -- no trusted fallback."""
    wd.train_with_progress(_tiny_config(tmp_path, _dataset(tmp_path)))

    for name in ("weeddet_best.pth", "weeddet_last.pth"):
        path = tmp_path / "ckpt" / name
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        assert checkpoint["epoch"] >= 1
        assert checkpoint["class_names"][0] == "rice_protect"
        assert checkpoint["best_metric_name"] == "train/total_loss"


def test_checkpoint_loads_in_a_clean_subprocess(tmp_path):
    """Load in a *separate* interpreter, the way the Colab eval cell does.

    In-process round-trips cannot catch a ``__main__``-scoped pickle: pytest's
    ``__main__`` happens to be importable. Only a fresh process reproduces the
    ``AttributeError: Can't get attribute '_RicesegBackboneInit'`` failure.
    """
    config = _tiny_config(tmp_path, _dataset(tmp_path))
    config["backbone_init"] = None  # exercised separately; keep this run cheap
    wd.train_with_progress(config)

    checkpoint_path = str(tmp_path / "ckpt" / "weeddet_best.pth")
    script = textwrap.dedent(f"""
        from agrinav.training.weeddet_train import load_checkpoint_model
        model = load_checkpoint_model({checkpoint_path!r}, device="cpu")
        print("classes", model.num_classes)
        """)
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, f"clean-process load failed:\n{result.stderr}"
    assert "classes 3" in result.stdout


def test_legacy_main_scoped_pickle_is_repaired(tmp_path):
    """A checkpoint whose config holds a ``__main__``-scoped callable still loads."""
    import __main__

    # Reproduce how the class pickles when training runs as `python -m ...`.
    __main__._LegacyBackboneInit = _RicesegBackboneInit
    _RicesegBackboneInit.__module__ = "__main__"
    _RicesegBackboneInit.__qualname__ = "_LegacyBackboneInit"
    try:
        payload = {
            "epoch": 3,
            "state_dict": {},
            "config": {"num_classes": 3, "backbone_init": _RicesegBackboneInit("/x.pth")},
        }
        path = tmp_path / "legacy.pth"
        torch.save(payload, path)

        with pytest.raises(Exception):
            torch.load(path, map_location="cpu", weights_only=True)

        # The repair path republishes the name, so full unpickling resolves it.
        from agrinav.training.weeddet_train import _alias_legacy_pickle_names

        _alias_legacy_pickle_names()
        restored = torch.load(path, map_location="cpu", weights_only=False)
        assert restored["epoch"] == 3
    finally:
        _RicesegBackboneInit.__module__ = "agrinav.training.weeddet_train"
        _RicesegBackboneInit.__qualname__ = "_RicesegBackboneInit"
        del __main__._LegacyBackboneInit


# --------------------------------------------------------------- run artifacts
def test_completed_run_writes_terminal_artifacts(tmp_path):
    """num_epochs=2 with save_every=4 writes no periodic file -- last.pth must exist.

    This is the exact arithmetic that made a finished 18-epoch run look like a
    crash at epoch 16.
    """
    wd.train_with_progress(_tiny_config(tmp_path, _dataset(tmp_path)))
    ckpt_dir = tmp_path / "ckpt"

    assert not (ckpt_dir / "weeddet_epoch2.pth").exists(), "2 % 4 != 0; no periodic file expected"
    assert (ckpt_dir / "weeddet_last.pth").exists()

    status = json.loads((ckpt_dir / "status.json").read_text(encoding="utf-8"))
    assert status["completed"] is True
    assert status["epochs_completed"] == status["epochs_planned"] == 2
    assert status["best_epoch"] in (1, 2)

    last = torch.load(ckpt_dir / "weeddet_last.pth", map_location="cpu", weights_only=True)
    assert last["epoch"] == 2, "weeddet_last.pth must hold the final epoch"


def test_metrics_jsonl_has_one_row_per_epoch(tmp_path):
    wd.train_with_progress(_tiny_config(tmp_path, _dataset(tmp_path)))

    rows = [
        json.loads(line)
        for line in (tmp_path / "ckpt" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["epoch"] for row in rows] == [1, 2]
    for row in rows:
        # Component losses were previously computed and thrown away in a tqdm postfix.
        assert row["train/cls_loss"] > 0
        assert row["train/reg_loss"] >= 0
        assert row["n_batches"] > 0
        assert row["select_metric"] == "train/total_loss"


# --------------------------------------------------------------- driver plumbing
def _val_args(tmp_path, **overrides):
    import argparse

    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    defaults = dict(
        ann_file=ann_file,
        images_root=images_root,
        val_ann_file=ann_file,
        val_images_root=images_root,
        config=None,
        class_names=None,
        riceseg_backbone=None,
        img_size=64,
        batch_size=None,
        epochs=1,
        base_lr=None,
        checkpoint_dir=str(tmp_path / "ckpt"),
        num_workers=0,
        save_every=None,
        repeat_factor=None,
        device="cpu",
        seed=42,
        bn_policy=None,
        no_pretrained_backbone=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_build_config_wires_the_val_split_unaugmented(tmp_path):
    from agrinav.training.weeddet_train import build_config

    config = build_config(_val_args(tmp_path))

    assert config["val_dataset"] is not None
    assert config["val_dataset"].augment is False, "val must not be augmented"
    assert config["train_dataset"].augment is True
    assert config["val_batch_size"] == config["batch_size"]


def test_model_defensively_resolves_none_val_batch_size():
    assert (
        wd._resolve_batch_size(  # noqa: SLF001 - regression-tests the internal guard
            {"batch_size": 8, "val_batch_size": None},
            "val_batch_size",
            fallback_key="batch_size",
        )
        == 8
    )


def test_cli_default_val_batch_size_runs_validation(tmp_path):
    """The CLI's None sentinel must not disable DataLoader auto-batching.

    This is the production failure path: ``build_config`` used to retain
    ``val_batch_size=None`` and ``train_with_progress`` passed it directly to
    DataLoader. The first validation sample then reached ``collate_fn`` as a
    raw ``(image, target)`` tuple and raised ``KeyError(0)`` before any epoch
    metrics or checkpoints could be written.
    """
    from agrinav.training.weeddet_train import build_config

    config = build_config(_val_args(tmp_path))
    assert config["val_batch_size"] == config["batch_size"] == 4

    wd.train_with_progress(config)

    rows = [
        json.loads(line)
        for line in (tmp_path / "ckpt" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["val/total_loss"] > 0


def test_build_config_rejects_a_half_specified_val_split(tmp_path):
    from agrinav.training.weeddet_train import build_config

    with pytest.raises(ValueError, match="must be given together"):
        build_config(_val_args(tmp_path, val_images_root=None))


def test_build_config_refuses_to_validate_on_the_sealed_test_split(tmp_path):
    """The test split must never drive checkpoint selection (CLAUDE.md 13.3)."""
    from agrinav.training.weeddet_train import build_config

    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    sealed = tmp_path / "test.coco.json"
    sealed.write_text((tmp_path / "train.coco.json").read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="sealed"):
        build_config(_val_args(tmp_path, val_ann_file=str(sealed), val_images_root=images_root))
    assert os.path.exists(ann_file)


def test_atomic_save_leaves_no_partial_file_on_failure(tmp_path):
    """A kill mid-write must not destroy the previous good checkpoint."""
    path = tmp_path / "ckpt.pth"
    wd.atomic_torch_save({"epoch": 1}, path)

    class _Unpicklable:
        def __reduce__(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        wd.atomic_torch_save({"bad": _Unpicklable()}, path)

    assert not (tmp_path / "ckpt.pth.tmp").exists(), "temp file left behind"
    assert torch.load(path, map_location="cpu", weights_only=True)["epoch"] == 1


# --------------------------------------------------------------- validation + gates
def test_val_dataset_drives_checkpoint_selection(tmp_path):
    dataset = _dataset(tmp_path)
    config = _tiny_config(tmp_path, dataset, val_dataset=dataset)
    wd.train_with_progress(config)

    rows = [
        json.loads(line)
        for line in (tmp_path / "ckpt" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        assert row["select_metric"] == "val/total_loss"
        # Both networks are scored, so EMA-vs-raw is answerable from the log.
        assert row["val_raw/total_loss"] > 0
        assert row["val_ema/total_loss"] > 0
        assert row["val/total_loss"] == row["val_ema/total_loss"]

    best = torch.load(tmp_path / "ckpt" / "weeddet_best.pth", map_location="cpu", weights_only=True)
    assert best["best_metric_name"] == "val/total_loss"


def test_val_ap_interval_selects_on_ap_and_higher_is_better(tmp_path):
    """AP selection must flip the comparison direction; loss selection is lower-better.

    Selecting on validation AP with a `<` comparison would silently keep the
    *worst* epoch, and on a randomly-initialised detector every AP is ~0.0, so a
    test that only checked "it ran" would not notice.
    """
    dataset = _dataset(tmp_path)
    config = _tiny_config(tmp_path, dataset, val_dataset=dataset, val_ap_interval=1)
    wd.train_with_progress(config)

    rows = [
        json.loads(line)
        for line in (tmp_path / "ckpt" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows, "no metrics rows written"
    for row in rows:
        assert row["select_metric"] == "val/AP"
        assert row["select_value"] == row["val/AP"]
        for key in ("val/AP", "val/AP50", "val/AP75", "val/AR100"):
            assert key in row, f"{key} missing from the epoch row"
        assert row["val/eval_seconds"] >= 0

    status = json.loads((tmp_path / "ckpt" / "status.json").read_text(encoding="utf-8"))
    assert status["best_metric_name"] == "val/AP"
    # Higher-is-better: the recorded best must be the maximum AP seen, not the min.
    assert status["best_metric_value"] == pytest.approx(max(row["val/AP"] for row in rows))

    best = torch.load(tmp_path / "ckpt" / "weeddet_best.pth", map_location="cpu", weights_only=True)
    assert best["best_metric_name"] == "val/AP"


def test_val_ap_interval_without_a_val_split_is_rejected(tmp_path):
    """Failing closed beats silently falling back to a weaker selection metric."""
    with pytest.raises(ValueError, match="requires a val_dataset"):
        wd.train_with_progress(_tiny_config(tmp_path, _dataset(tmp_path), val_ap_interval=1))


def test_val_loss_selection_is_unchanged_when_ap_is_off(tmp_path):
    dataset = _dataset(tmp_path)
    wd.train_with_progress(_tiny_config(tmp_path, dataset, val_dataset=dataset, val_ap_interval=0))
    status = json.loads((tmp_path / "ckpt" / "status.json").read_text(encoding="utf-8"))
    assert status["best_metric_name"] == "val/total_loss"


def test_validation_does_not_update_batchnorm_statistics(tmp_path):
    """Validation must not leak into BN running stats (apply_bn_policy's warning)."""
    dataset = _dataset(tmp_path)
    model = wd.WeedDet(num_classes=3)
    model.train()
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=2, collate_fn=wd.collate_fn, num_workers=0
    )
    bn = next(m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d))
    before = bn.running_mean.clone()

    wd.evaluate_val_loss(model, loader, "cpu")

    assert torch.equal(bn.running_mean, before)
    assert model.training, "eval pass must restore train mode"


def test_nonfinite_loss_aborts_with_actionable_message(tmp_path, monkeypatch):
    """A NaN loss must fail loudly, not silently freeze `best` for the whole run."""
    dataset = _dataset(tmp_path)
    real_forward = wd.WeedDet.forward

    def _nan_forward(self, images, targets=None):
        result = real_forward(self, images, targets)
        if isinstance(result, dict):
            result["total_loss"] = result["total_loss"] * float("nan")
        return result

    monkeypatch.setattr(wd.WeedDet, "forward", _nan_forward)
    with pytest.raises(RuntimeError, match="non-finite training loss"):
        wd.train_with_progress(_tiny_config(tmp_path, dataset))


class _FakeFullBackboneInit:
    """Stands in for `_RicesegBackboneInit`: fills every backbone BN buffer.

    A callable that loaded nothing no longer suffices. The freeze predicate now
    asks each BatchNorm whether its running buffers hold loaded statistics rather
    than matching layer names, so "a backbone was injected" must actually leave
    statistics behind for `freeze_pretrained` to have anything to freeze.
    """

    def __call__(self, model):
        n = 0
        for name, module in model.named_modules():
            if not isinstance(module, torch.nn.BatchNorm2d) or not name.startswith("backbone."):
                continue
            with torch.no_grad():
                module.running_mean.fill_(0.37)
                module.running_var.fill_(1.9)
                module.num_batches_tracked.fill_(1234)
            n += 1
        return n


def test_bn_policy_makes_the_ab_single_factor(tmp_path):
    """`bn_policy` decouples BN trainability from which backbone was injected."""
    dataset = _dataset(tmp_path)

    calls = []
    real_policy = wd.apply_bn_policy
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        wd, "apply_bn_policy", lambda *a, **k: (calls.append(1), real_policy(*a, **k))[1]
    )
    try:
        # Injected-backbone arm with BN forced trainable = the matched control
        # for the same backbone frozen. Both arms load identical weights, so BN
        # trainability is the only factor that varies.
        config = _tiny_config(
            tmp_path,
            dataset,
            bn_policy="trainable",
            num_epochs=1,
            backbone_init=_FakeFullBackboneInit(),
        )
        wd.train_with_progress(config)
        assert calls == [], "bn_policy='trainable' must never freeze BN"
        assert config["bn_policy_resolved"] == "trainable"

        calls.clear()
        config = _tiny_config(
            tmp_path,
            dataset,
            bn_policy="freeze_pretrained",
            num_epochs=1,
            backbone_init=_FakeFullBackboneInit(),
            checkpoint_dir=str(tmp_path / "ckpt2"),
        )
        wd.train_with_progress(config)
        assert calls, "bn_policy='freeze_pretrained' must apply the BN freeze"
        assert config["bn_policy_resolved"] == "freeze_pretrained"
        assert config["bn_frozen_layers"] == 57
    finally:
        monkey.undo()


def test_invalid_bn_policy_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="bn_policy must be"):
        wd.train_with_progress(_tiny_config(tmp_path, _dataset(tmp_path), bn_policy="nope"))
