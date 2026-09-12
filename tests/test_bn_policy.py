"""CPU-only tests for the BatchNorm freeze policy and its scope.

`--bn-policy freeze_pretrained` was a silent no-op on the arm it mattered most
for. ``build_config`` sets ``pretrained_backbone=False`` whenever
``--riceseg-backbone`` is used, ``train_with_progress`` passed that straight into
``apply_bn_policy(pretrained_loaded=...)``, and that function froze only
``if pretrained_loaded and name.startswith(_PRETRAINED_PREFIXES)``. Measured
2026-07-31: **0 of 58** layers frozen on the RiceSEG arm, 48 of 58 on the
ImageNet arm -- while the run printed ``[bn-policy] freeze_pretrained ->
freeze_pretrained`` as though it had worked.

Fixing the flag exposed a second, subtler error in the same function. The name
list ``_PRETRAINED_PREFIXES`` answers "which layers can torchvision resnet50
weights fill?" -- 48 of the 57 backbone BN layers, excluding the custom stem and
layer1.0. ``load_riceseg_backbone`` fills the whole backbone, all 342 tensors
including every BN buffer, so under an injected backbone those nine layers hold
in-domain statistics that the name list still called random-init. Freezing by
name therefore left 9 of 57 backbone BN layers updating their statistics from
batches of 8.

The predicate is now empirical: :func:`bn_carries_pretrained_stats` asks each
module whether its running buffers differ from initialisation. That is correct
for both loaders, and ``expect_scope`` turns the answer into a fail-closed
assertion so a partial load cannot pass as a full one.

Consequence worth stating: a freshly constructed model now freezes **nothing**,
where the old name-based code froze 48. That old behaviour was the hazard its
own docstring warned about -- freezing BN at random init makes it a permanent
identity op -- so the fakes below write real statistics instead of standing in
for a load that never happened.
"""

import json

import pytest
import torch
from test_weeddet_train import _write_synthetic_split  # noqa: F401  (shared fixture builder)

from agrinav.models import weeddet_v6b as wd
from agrinav.training.weeddet_train import _CocoSplitDataset

pytestmark = pytest.mark.unit

CLASS_NAMES = ("rice_protect", "weed_target", "non_target_aquatic")

# Measured on WeedDet(num_classes=2/3) -- the head BN count does not vary with
# num_classes. Asserted directly in test_bn_layer_inventory so a change to the
# architecture fails there with an explanation rather than everywhere at once.
N_BN_TOTAL = 58
N_BN_BACKBONE = 57
N_BN_IMAGENET = 48


def _bn_counts(model):
    """(frozen, trainable) BatchNorm modules. Never call model.train() after this."""
    bns = [m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d)]
    frozen = sum(1 for m in bns if not m.training)
    return frozen, len(bns) - frozen


def _fill_bn_stats(model, predicate):
    """Write non-default running statistics into every BN whose name matches.

    Stands in for a checkpoint load: what makes a layer "pretrained" is that its
    buffers hold real statistics, and that is exactly what a load leaves behind.
    Returns the names touched.
    """
    touched = []
    for name, module in model.named_modules():
        if not isinstance(module, torch.nn.BatchNorm2d) or not predicate(name):
            continue
        with torch.no_grad():
            module.running_mean.fill_(0.37)
            module.running_var.fill_(1.9)
            module.num_batches_tracked.fill_(1234)
        touched.append(name)
    return touched


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


class _FakeFullBackboneInit:
    """Stands in for `_RicesegBackboneInit`: fills EVERY backbone BN buffer.

    ``load_riceseg_backbone`` requires all 342 ``backbone.*`` tensors to be
    present with matching shapes or it raises, so a successful injection means
    every backbone BN carries in-domain statistics -- including the stem and
    layer1.0 layers ImageNet cannot reach. Writing the buffers here exercises the
    real predicate without a 94 MB checkpoint.
    """

    def __call__(self, model):
        return len(_fill_bn_stats(model, lambda name: name.startswith("backbone.")))

    def __repr__(self):
        return "_FakeFullBackboneInit()"


class _FakePartialBackboneInit:
    """A backbone load that silently covered only part of the backbone."""

    def __call__(self, model):
        return len(_fill_bn_stats(model, lambda name: name.startswith("backbone.layer4")))

    def __repr__(self):
        return "_FakePartialBackboneInit()"


def _fake_imagenet_load(model, **_kwargs):
    """Stub for ``load_imagenet_backbone``: fills exactly the layers it can fill.

    The real one downloads ~100 MB of torchvision weights; these tests assert
    policy resolution, not the key mapping (covered in test_weeddet_v6b_fixes).
    """
    names = _fill_bn_stats(model, lambda name: name.startswith(wd._PRETRAINED_PREFIXES))
    return len(names), 0


# --------------------------------------------------------------------------- #
# inventory: the numbers every other assertion in this file depends on
# --------------------------------------------------------------------------- #
def test_bn_layer_inventory():
    """Pins the architecture facts the freeze scopes are defined against."""
    model = wd.WeedDet(num_classes=2)
    names = [n for n, m in model.named_modules() if isinstance(m, torch.nn.BatchNorm2d)]
    backbone = [n for n in names if n.startswith("backbone.")]
    assert len(names) == N_BN_TOTAL
    assert len(backbone) == N_BN_BACKBONE
    # Exactly one BN outside the backbone, and it is randomly initialised: it has
    # no pretrained statistics under any loader, so no scope may freeze it.
    assert [n for n in names if not n.startswith("backbone.")] == ["head.shared.2.seq.3"]
    assert len(wd.bn_scope_names(model, "backbone")) == N_BN_BACKBONE
    assert len(wd.bn_scope_names(model, "imagenet")) == N_BN_IMAGENET
    # The 9-layer gap is the bug: stem + layer1.0, in-domain under RiceSEG,
    # unreachable by ImageNet.
    gap = wd.bn_scope_names(model, "backbone") - wd.bn_scope_names(model, "imagenet")
    assert len(gap) == 9
    assert all(n.startswith(("backbone.stem", "backbone.layer1.0")) for n in gap)


# --------------------------------------------------------------------------- #
# the predicate: loaded statistics, not layer names
# --------------------------------------------------------------------------- #
def test_a_fresh_batchnorm_is_not_pretrained():
    """Init defaults (mean 0, var 1, 0 batches) must never count as loaded.

    This is the guard against the old failure mode: freezing a randomly
    initialised BN pins it to an identity transform for the whole run.
    """
    assert not wd.bn_carries_pretrained_stats(torch.nn.BatchNorm2d(8))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda m: m.running_mean.fill_(0.1), id="mean"),
        pytest.param(lambda m: m.running_var.fill_(2.0), id="var"),
        pytest.param(lambda m: m.num_batches_tracked.fill_(5), id="num_batches_tracked"),
    ],
)
def test_any_departure_from_init_counts_as_pretrained(mutate):
    """Some exports drop num_batches_tracked; any one signal is enough."""
    module = torch.nn.BatchNorm2d(8)
    with torch.no_grad():
        mutate(module)
    assert wd.bn_carries_pretrained_stats(module)


def test_apply_bn_policy_freezes_nothing_on_an_unloaded_model():
    """The behaviour change, asserted explicitly rather than left implicit."""
    model = wd.WeedDet(num_classes=2)
    model.train()
    assert wd.apply_bn_policy(model, pretrained_loaded=True) == (0, N_BN_TOTAL)


def test_pretrained_loaded_false_is_still_a_master_switch():
    model = wd.WeedDet(num_classes=2)
    _fill_bn_stats(model, lambda name: name.startswith("backbone."))
    model.train()
    assert wd.apply_bn_policy(model, pretrained_loaded=False) == (0, N_BN_TOTAL)


def test_the_freeze_set_must_be_resolved_before_training_moves_the_buffers():
    """Why resolve/apply are separate functions.

    One training step gives a randomly initialised BN real running statistics.
    Re-deriving the set afterwards therefore sweeps the head BN in and pins it to
    whatever that first step produced -- a silent scope change mid-run.
    """
    model = wd.WeedDet(num_classes=2)
    _fill_bn_stats(model, lambda name: name.startswith("backbone."))
    at_setup = wd.resolve_bn_freeze_names(model, expect_scope="backbone")
    assert len(at_setup) == N_BN_BACKBONE

    head = model.get_submodule("head.shared.2.seq.3")
    head.train()
    with torch.no_grad():  # one forward is enough to update the buffers
        head(torch.randn(2, head.num_features, 4, 4))

    assert wd.bn_carries_pretrained_stats(head), "precondition: the buffers moved"
    assert len(wd.resolve_bn_freeze_names(model)) == N_BN_TOTAL
    # Applying the set resolved at setup keeps the head trainable regardless.
    frozen, trainable = wd.apply_bn_policy(model, freeze_names=at_setup)
    assert (frozen, trainable) == (N_BN_BACKBONE, 1)


def test_apply_bn_policy_is_idempotent_given_a_resolved_set():
    """Re-application every epoch must converge, not creep."""
    model = wd.WeedDet(num_classes=2)
    _fill_bn_stats(model, lambda name: name.startswith("backbone."))
    names = wd.resolve_bn_freeze_names(model, expect_scope="backbone")
    first = wd.apply_bn_policy(model, freeze_names=names)
    model.train()
    second = wd.apply_bn_policy(model, freeze_names=names)
    assert first == second == (N_BN_BACKBONE, 1)


# --------------------------------------------------------------------------- #
# the regression: freezing must not depend on which backbone was loaded
# --------------------------------------------------------------------------- #
def test_freeze_pretrained_covers_the_whole_backbone_on_the_injected_arm(tmp_path):
    """The audit's item 1: all 57 backbone BN, leaving the random head BN alone.

    The first fix took this from 0 to 48; 48 still left the stem and layer1.0
    updating their statistics from batches of 8, which is the mechanism under
    investigation.
    """
    dataset = _dataset(tmp_path)
    config = _config(
        tmp_path, dataset, bn_policy="freeze_pretrained", backbone_init=_FakeFullBackboneInit()
    )
    wd.train_with_progress(config)
    assert config["bn_frozen_layers"] == N_BN_BACKBONE
    assert config["bn_trainable_layers"] == N_BN_TOTAL - N_BN_BACKBONE == 1
    assert config["bn_freeze_scope"] == "backbone"


def test_the_one_trainable_layer_is_the_random_head_bn(tmp_path):
    """Named, not just counted: freezing this one would pin it at random init."""
    dataset = _dataset(tmp_path)
    model = wd.train_with_progress(
        _config(
            tmp_path,
            dataset,
            bn_policy="freeze_pretrained",
            backbone_init=_FakeFullBackboneInit(),
        )
    )
    still_training = [
        name
        for name, module in model.named_modules()
        if isinstance(module, torch.nn.BatchNorm2d) and module.training
    ]
    assert still_training == ["head.shared.2.seq.3"]


def test_freeze_pretrained_on_the_imagenet_arm_covers_what_imagenet_filled(tmp_path, monkeypatch):
    """48, not 57: the stem and layer1.0 really are random here."""
    monkeypatch.setattr(wd, "load_imagenet_backbone", _fake_imagenet_load)
    dataset = _dataset(tmp_path)
    config = _config(tmp_path, dataset, bn_policy="freeze_pretrained", pretrained_backbone=True)
    wd.train_with_progress(config)
    assert config["bn_frozen_layers"] == N_BN_IMAGENET
    assert config["bn_trainable_layers"] == N_BN_TOTAL - N_BN_IMAGENET
    assert config["bn_freeze_scope"] == "imagenet"


def test_the_two_arms_freeze_different_counts_and_that_is_correct(tmp_path, monkeypatch):
    """A matched A/B cannot assume equal counts -- the arms differ in what loaded.

    Stated as a test because the earlier version of this file asserted the two
    arms must be equal, which was true only while both were being measured by
    the same (wrong) name list.
    """
    monkeypatch.setattr(wd, "load_imagenet_backbone", _fake_imagenet_load)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    imagenet = _config(
        tmp_path / "a",
        _dataset(tmp_path / "a"),
        bn_policy="freeze_pretrained",
        pretrained_backbone=True,
    )
    injected = _config(
        tmp_path / "b",
        _dataset(tmp_path / "b"),
        bn_policy="freeze_pretrained",
        backbone_init=_FakeFullBackboneInit(),
    )
    wd.train_with_progress(imagenet)
    wd.train_with_progress(injected)
    assert imagenet["bn_frozen_layers"] == N_BN_IMAGENET
    assert injected["bn_frozen_layers"] == N_BN_BACKBONE


# --------------------------------------------------------------------------- #
# the freeze must survive the epoch loop
# --------------------------------------------------------------------------- #
def test_the_freeze_survives_model_train_each_epoch(tmp_path):
    """`model.train()` re-enables every BN; the loop must re-apply the policy."""
    dataset = _dataset(tmp_path)
    config = _config(
        tmp_path,
        dataset,
        num_epochs=2,
        bn_policy="freeze_pretrained",
        backbone_init=_FakeFullBackboneInit(),
    )
    model = wd.train_with_progress(config)
    frozen, trainable = _bn_counts(model)
    assert frozen == N_BN_BACKBONE, f"BN unfroze during training: {frozen}/{trainable}"


def test_frozen_backbone_running_stats_do_not_move(tmp_path):
    """The point of freezing, verified on the buffers rather than the mode flag."""
    dataset = _dataset(tmp_path)
    config = _config(
        tmp_path,
        dataset,
        num_epochs=2,
        bn_policy="freeze_pretrained",
        backbone_init=_FakeFullBackboneInit(),
    )
    model = wd.train_with_progress(config)
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.BatchNorm2d) and name.startswith("backbone."):
            assert torch.allclose(module.running_mean, torch.full_like(module.running_mean, 0.37))
            assert torch.allclose(module.running_var, torch.full_like(module.running_var, 1.9))
            assert int(module.num_batches_tracked) == 1234


# --------------------------------------------------------------------------- #
# fail closed rather than pretend
# --------------------------------------------------------------------------- #
def test_a_partial_backbone_load_is_a_scope_error(tmp_path):
    """A load that covered only layer4 must not pass as a full-backbone freeze.

    Without this the run trains on, freezing a fraction of the intended layers,
    and the config records a scope it did not achieve.
    """
    dataset = _dataset(tmp_path)
    with pytest.raises(ValueError, match="BN freeze scope mismatch"):
        wd.train_with_progress(
            _config(
                tmp_path,
                dataset,
                bn_policy="freeze_pretrained",
                backbone_init=_FakePartialBackboneInit(),
            )
        )


def test_scope_error_names_the_layers_it_could_not_freeze(tmp_path):
    """An actionable failure: which layers, and why it refuses to continue."""
    model = wd.WeedDet(num_classes=2)
    _fill_bn_stats(model, lambda name: name.startswith("backbone.layer4"))
    with pytest.raises(ValueError) as excinfo:
        wd.resolve_bn_freeze_names(model, expect_scope="backbone")
    message = str(excinfo.value)
    assert "not_frozen=" in message
    # Sorted, so the sample starts at layer1.0 -- one of the nine layers ImageNet
    # cannot reach and a full backbone load must fill.
    assert "backbone.layer1.0" in message
    assert "found 10 layers" in message and "expected the 57" in message
    assert "identity op" in message


def test_declaring_the_imagenet_scope_for_a_full_backbone_is_an_error():
    """Mismatch is caught in both directions, not just under-freezing."""
    model = wd.WeedDet(num_classes=2)
    _fill_bn_stats(model, lambda name: name.startswith("backbone."))
    with pytest.raises(ValueError, match="unexpectedly_frozen="):
        wd.resolve_bn_freeze_names(model, expect_scope="imagenet")


def test_freeze_pretrained_with_nothing_to_freeze_is_an_error(tmp_path):
    """Asking to freeze pretrained BN when none exists must not run silently.

    That run would be byte-identical to bn_policy='trainable' while its config
    and log both claimed otherwise -- which is how 90 minutes of A100 time gets
    spent reproducing a result you were trying to change.
    """
    dataset = _dataset(tmp_path)
    with pytest.raises(ValueError, match="froze 0 BatchNorm layers"):
        wd.train_with_progress(
            _config(tmp_path, dataset, bn_policy="freeze_pretrained", pretrained_backbone=False)
        )


def test_an_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="bn scope must be"):
        wd.bn_scope_names(wd.WeedDet(num_classes=2), "everything")


def test_auto_with_a_scratch_backbone_still_runs(tmp_path):
    """'auto' + no pretrained weights legitimately freezes nothing; do not break it."""
    dataset = _dataset(tmp_path)
    config = _config(tmp_path, dataset, bn_policy="auto", pretrained_backbone=False)
    wd.train_with_progress(config)
    assert config["bn_frozen_layers"] == 0
    assert config["bn_policy_resolved"] == "freeze_pretrained"


def test_trainable_policy_freezes_nothing(tmp_path):
    dataset = _dataset(tmp_path)
    config = _config(
        tmp_path, dataset, bn_policy="trainable", backbone_init=_FakeFullBackboneInit()
    )
    model = wd.train_with_progress(config)
    frozen, trainable = _bn_counts(model)
    assert config["bn_frozen_layers"] == 0
    assert frozen == 0 and trainable == N_BN_TOTAL


# --------------------------------------------------------------------------- #
# the counts are recorded, so a run can be audited after the fact
# --------------------------------------------------------------------------- #
def test_bn_counts_land_in_the_saved_config(tmp_path):
    """The 2026-07-30 run could not be checked for this without re-deriving it."""
    dataset = _dataset(tmp_path)
    config = _config(
        tmp_path, dataset, bn_policy="freeze_pretrained", backbone_init=_FakeFullBackboneInit()
    )
    wd.train_with_progress(config)

    ckpt = torch.load(
        tmp_path / "ckpt" / "weeddet_last.pth", map_location="cpu", weights_only=False
    )
    saved = ckpt["config"]
    assert saved["bn_frozen_layers"] == N_BN_BACKBONE
    assert saved["bn_trainable_layers"] == 1
    assert saved["bn_policy_resolved"] == "freeze_pretrained"
    assert saved["bn_freeze_scope"] == "backbone"


def test_bn_state_report_lands_in_metrics_jsonl(tmp_path):
    """Per-epoch observed state, not just what the policy claimed at setup."""
    dataset = _dataset(tmp_path)
    config = _config(
        tmp_path, dataset, bn_policy="freeze_pretrained", backbone_init=_FakeFullBackboneInit()
    )
    wd.train_with_progress(config)
    rows = [
        json.loads(line)
        for line in (tmp_path / "ckpt" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert rows[-1]["bn/total"] == N_BN_TOTAL
    assert rows[-1]["bn/eval_mode"] == N_BN_BACKBONE
    assert rows[-1]["bn/backbone_eval_mode"] == N_BN_BACKBONE
    assert rows[-1]["bn/grad_off"] == N_BN_BACKBONE


def test_bn_state_report_sees_an_unfrozen_model():
    """The report describes the model, not the intent -- otherwise it is useless."""
    model = wd.WeedDet(num_classes=2)
    model.train()
    report = wd.bn_state_report(model)
    assert report["bn/eval_mode"] == 0
    assert report["bn/train_mode"] == N_BN_TOTAL
    assert report["bn/grad_off"] == 0
