"""CPU-only tests for training/weeddet_train.py -- no network, no large data.

Covers the Phase-2 detector driver seams:
  * ``_CocoSplitDataset`` resolves ``images_root + file_name`` (incl. a nested
    file_name) and returns box/label-aligned targets, mapping a NON-contiguous
    COCO category id (4) to its contiguous index (2);
  * ``--self-test`` runs a finite forward+backward and returns 0;
  * an injected dataset actually drives ``train_with_progress`` (the one-line
    monolith seam) for a single tiny CPU step and writes a checkpoint.
"""

import argparse
import json
import os
import pickle

import pytest
import torch
from PIL import Image

from agrinav.models import weeddet_v6b as wd
from agrinav.training.weeddet_train import (
    DEFAULT_CLASS_NAMES,
    _CocoSplitDataset,
    _HARD_DEFAULTS,
    _build_parser,
    _make_riceseg_backbone_init,
    build_config,
    load_checkpoint_model,
    main,
    predict_image,
    run_self_test,
)

# Non-contiguous category ids on purpose ({1,2,4}) -- mirrors the real split.
_CATEGORIES = [
    {"id": 1, "name": "rice_protect"},
    {"id": 2, "name": "weed_target"},
    {"id": 4, "name": "non_target_aquatic"},
]


def _write_synthetic_split(root, img_size=64):
    """Write 2 solid-colour jpgs + a matching COCO json; return (ann_file, images_root).

    image 0 (flat file_name): rice_protect (cat 1) + non_target_aquatic (cat 4)
    image 1 (nested file_name 'sub/img1.jpg'): weed_target (cat 2)
    """
    images_root = os.path.join(root, "images")
    os.makedirs(os.path.join(images_root, "sub"), exist_ok=True)
    Image.new("RGB", (img_size, img_size), (20, 120, 40)).save(
        os.path.join(images_root, "img0.jpg")
    )
    Image.new("RGB", (img_size, img_size), (120, 40, 20)).save(
        os.path.join(images_root, "sub", "img1.jpg")
    )

    coco = {
        "categories": _CATEGORIES,
        "images": [
            {"id": 10, "file_name": "img0.jpg", "width": img_size, "height": img_size},
            {"id": 11, "file_name": "sub/img1.jpg", "width": img_size, "height": img_size},
        ],
        "annotations": [
            # image 10: cat 1 -> idx 0, cat 4 -> idx 2  (xywh boxes)
            {"id": 1, "image_id": 10, "category_id": 1, "bbox": [5, 5, 15, 15], "iscrowd": 0},
            {"id": 2, "image_id": 10, "category_id": 4, "bbox": [30, 30, 20, 20], "iscrowd": 0},
            # image 11: cat 2 -> idx 1
            {"id": 3, "image_id": 11, "category_id": 2, "bbox": [10, 10, 25, 25], "iscrowd": 0},
        ],
    }
    ann_file = os.path.join(root, "train.coco.json")
    with open(ann_file, "w", encoding="utf-8") as handle:
        json.dump(coco, handle)
    return ann_file, images_root


def test_dataset_resolves_paths_and_maps_noncontiguous_categories(tmp_path):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    dataset = _CocoSplitDataset(
        ann_file, images_root, DEFAULT_CLASS_NAMES, img_size=64, augment=False
    )

    assert len(dataset) == 2

    img_tensor, target = dataset[0]
    assert tuple(img_tensor.shape) == (3, 64, 64)
    # cat 1 -> 0 and NON-contiguous cat 4 -> 2, both present and aligned with boxes.
    assert sorted(target["labels"].tolist()) == [0, 2]
    assert target["boxes"].shape[0] == target["labels"].shape[0] == 2
    assert float(target["boxes"].min()) >= 0.0
    assert float(target["boxes"].max()) <= 64.0

    # items() (inherited) resolves images_root + file_name, including the nested one.
    resolved = dataset.items()
    assert len(resolved) == 2
    for image_id, path, width, height in resolved:
        assert os.path.isfile(path), f"unresolved image path for id={image_id}: {path}"
        assert (width, height) == (64, 64)


def test_dataset_limit_and_class_subset(tmp_path):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))

    limited = _CocoSplitDataset(ann_file, images_root, DEFAULT_CLASS_NAMES, img_size=64, limit=1)
    assert len(limited) == 1

    # Selecting only weed_target keeps image 11's single ann, remapped to idx 0.
    weed_only = _CocoSplitDataset(ann_file, images_root, ("weed_target",), img_size=64)
    _, target = weed_only[1]
    assert target["labels"].tolist() == [0]


def test_dataset_missing_ann_file_raises_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="annotation file not found"):
        _CocoSplitDataset(str(tmp_path / "nope.json"), str(tmp_path), DEFAULT_CLASS_NAMES)


def test_self_test_returns_zero_with_finite_losses():
    assert run_self_test() == 0
    assert main(["--self-test"]) == 0


def test_build_config_round_trips_through_pickle(tmp_path):
    """The full config (dataset included) must survive pickling -- checkpoints embed it."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    args = argparse.Namespace(
        ann_file=ann_file,
        images_root=images_root,
        config=None,
        no_pretrained_backbone=True,
    )
    cfg = build_config(args)
    assert isinstance(cfg["train_dataset"], _CocoSplitDataset)

    restored = pickle.loads(pickle.dumps(cfg))
    assert restored["num_classes"] == cfg["num_classes"]
    assert restored["class_names"] == cfg["class_names"]
    assert len(restored["train_dataset"]) == len(cfg["train_dataset"])


def test_load_checkpoint_model_reads_dataset_bearing_checkpoint(tmp_path):
    """Checkpoints embed the dataset in config; torch >= 2.6 strict default must not break load."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    dataset = _CocoSplitDataset(
        ann_file, images_root, DEFAULT_CLASS_NAMES, img_size=64, augment=False
    )
    model = wd.WeedDet(num_classes=3)
    ckpt = str(tmp_path / "dataset_bearing.pth")
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": {"num_classes": 3, "train_dataset": dataset},
        },
        ckpt,
    )

    loaded = load_checkpoint_model(ckpt, device="cpu")
    assert not loaded.training  # eval mode


@pytest.mark.integration
def test_injected_dataset_drives_train_with_progress(tmp_path):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    dataset = _CocoSplitDataset(
        ann_file, images_root, DEFAULT_CLASS_NAMES, img_size=64, augment=False
    )
    ckpt_dir = str(tmp_path / "ckpt")
    config = {
        "device": "cpu",
        "seed": 0,
        "num_classes": 3,
        "pretrained_backbone": False,  # no ImageNet fetch (offline)
        "img_size": 64,
        "batch_size": 2,
        "num_workers": 0,
        "base_lr": 0.01,
        "num_epochs": 1,
        "save_every": 99,  # skip the periodic checkpoint; best-checkpoint still writes
        "repeat_factor": 1,
        "use_amp": False,
        "use_ema": False,
        "grad_clip": 0.5,
        "checkpoint_dir": ckpt_dir,
        "train_dataset": dataset,  # the injected seam under test
    }

    model = wd.train_with_progress(config)
    assert model is not None
    ckpt_path = os.path.join(ckpt_dir, "weeddet_best.pth")
    assert os.path.isfile(ckpt_path)

    # Full inference seam: reload the real checkpoint via the helper (must
    # survive the torch >= 2.6 weights_only default) and run one prediction.
    loaded = load_checkpoint_model(ckpt_path, device="cpu")
    _, boxes, scores, labels = predict_image(
        loaded, os.path.join(images_root, "img0.jpg"), img_size=64, score_thr=0.0
    )
    assert boxes.shape[0] == scores.shape[0] == labels.shape[0]


# ================================================================ backbone seam
def _riceseg_style_backbone(tmp_path, num_classes=3, corrupt=False, drop=False):
    """Export a WeedDet's own backbone tensors, the way riceseg_pretrain does.

    Round-tripping the model's real keys is what makes this a meaningful test of
    the fail-closed contract: `drop` removes a tensor and `corrupt` reshapes one,
    which are exactly the two failure modes load_riceseg_backbone must reject.
    """
    model = wd.WeedDet(num_classes=num_classes)
    sd = {k: v.cpu() for k, v in model.state_dict().items() if k.startswith("backbone.")}
    if drop:
        del sd[sorted(sd)[0]]
    if corrupt:
        k = sorted(sd)[0]
        sd[k] = torch.zeros(1)
    path = str(tmp_path / f"bk_{'bad' if (corrupt or drop) else 'ok'}.pth")
    torch.save(sd, path)
    return path


def test_riceseg_backbone_init_loads_and_is_picklable(tmp_path):
    """The init callable must load real weights AND survive the checkpoint pickle."""
    ckpt = _riceseg_style_backbone(tmp_path)
    init = _make_riceseg_backbone_init(ckpt)

    model = wd.WeedDet(num_classes=3)
    n_loaded = init(model)
    assert n_loaded > 0

    # train_with_progress pickles the whole config into every checkpoint.
    restored = pickle.loads(pickle.dumps(init))
    assert restored.ckpt_path == init.ckpt_path
    restored(wd.WeedDet(num_classes=3))  # still usable after the round-trip


def test_riceseg_backbone_missing_path_fails_before_training(tmp_path):
    with pytest.raises(FileNotFoundError, match="riceseg-backbone checkpoint not found"):
        _make_riceseg_backbone_init(str(tmp_path / "nope.pth"))


@pytest.mark.parametrize("kind", ["drop", "corrupt"])
def test_riceseg_backbone_partial_or_mismatched_load_raises(tmp_path, kind):
    """Fails closed: never silently train from a mostly-random backbone."""
    ckpt = _riceseg_style_backbone(tmp_path, drop=(kind == "drop"), corrupt=(kind == "corrupt"))
    init = _make_riceseg_backbone_init(ckpt)
    with pytest.raises(ValueError, match="riceseg load is incomplete"):
        init(wd.WeedDet(num_classes=3))


def test_build_config_wires_backbone_init_and_disables_imagenet(tmp_path):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    ckpt = _riceseg_style_backbone(tmp_path)
    args = argparse.Namespace(
        ann_file=ann_file,
        images_root=images_root,
        config=None,
        no_pretrained_backbone=False,
        riceseg_backbone=ckpt,
    )
    cfg = build_config(args)
    assert callable(cfg["backbone_init"])
    # ImageNet must be recorded off so the saved config is unambiguous.
    assert cfg["pretrained_backbone"] is False


def test_build_config_without_riceseg_backbone_has_no_seam(tmp_path):
    """Absent flag -> no backbone_init key, so the monolith path is unchanged."""
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    args = argparse.Namespace(
        ann_file=ann_file, images_root=images_root, config=None, no_pretrained_backbone=True
    )
    cfg = build_config(args)
    assert cfg.get("backbone_init") is None


@pytest.mark.integration
def test_injected_backbone_drives_training_and_keeps_bn_trainable(tmp_path):
    """End-to-end: the seam loads the backbone and leaves BN trainable.

    apply_bn_policy would freeze the ImageNet-prefixed BN layers; the RiceSEG
    stats are in-domain, so load_riceseg_backbone documents that it must NOT be
    applied. Assert no backbone BN got frozen.
    """
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    dataset = _CocoSplitDataset(
        ann_file, images_root, DEFAULT_CLASS_NAMES, img_size=64, augment=False
    )
    ckpt = _riceseg_style_backbone(tmp_path)
    ckpt_dir = str(tmp_path / "ckpt_bk")
    config = {
        "device": "cpu",
        "seed": 0,
        "num_classes": 3,
        "backbone_init": _make_riceseg_backbone_init(ckpt),
        "img_size": 64,
        "batch_size": 2,
        "num_workers": 0,
        "base_lr": 0.01,
        "num_epochs": 1,
        "save_every": 99,
        "repeat_factor": 1,
        "use_amp": False,
        "use_ema": False,
        "grad_clip": 0.5,
        "checkpoint_dir": ckpt_dir,
        "train_dataset": dataset,
    }

    model = wd.train_with_progress(config)
    assert model is not None
    assert os.path.isfile(os.path.join(ckpt_dir, "weeddet_best.pth"))

    frozen = [
        name
        for name, m in model.named_modules()
        if name.startswith("backbone.")
        and isinstance(m, torch.nn.BatchNorm2d)
        and not any(p.requires_grad for p in m.parameters())
    ]
    assert not frozen, f"backbone BN must stay trainable for a RiceSEG init; frozen={frozen[:4]}"


@pytest.mark.integration
def test_backbone_seam_toggles_apply_bn_policy_exactly(tmp_path, monkeypatch):
    """The seam's contract, asserted directly rather than inferred.

    Absent ``backbone_init`` -> the original ImageNet/BN path still runs
    (apply_bn_policy called at init AND once per epoch). Present -> skipped
    entirely, because the in-domain BN stats must stay trainable.
    """
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    dataset = _CocoSplitDataset(
        ann_file, images_root, DEFAULT_CLASS_NAMES, img_size=64, augment=False
    )
    base = {
        "device": "cpu",
        "seed": 0,
        "num_classes": 3,
        "pretrained_backbone": False,  # offline: no ImageNet fetch
        "img_size": 64,
        "batch_size": 2,
        "num_workers": 0,
        "base_lr": 0.01,
        "num_epochs": 2,  # >1 so the per-epoch call site is exercised
        "save_every": 99,
        "repeat_factor": 1,
        "use_amp": False,
        "use_ema": False,
        "grad_clip": 0.5,
        "train_dataset": dataset,
    }

    calls = []
    real = wd.apply_bn_policy
    monkeypatch.setattr(wd, "apply_bn_policy", lambda *a, **k: (calls.append(1), real(*a, **k))[1])

    wd.train_with_progress({**base, "checkpoint_dir": str(tmp_path / "a")})
    without_seam = len(calls)
    assert without_seam >= 3, "original path must call apply_bn_policy at init + each epoch"

    calls.clear()
    ckpt = _riceseg_style_backbone(tmp_path)
    wd.train_with_progress(
        {
            **base,
            "checkpoint_dir": str(tmp_path / "b"),
            "backbone_init": _make_riceseg_backbone_init(ckpt),
        }
    )
    assert calls == [], "an injected in-domain backbone must never be BN-frozen"


def _grad_clip_args(tmp_path, **extra):
    ann_file, images_root = _write_synthetic_split(str(tmp_path))
    return argparse.Namespace(
        ann_file=ann_file,
        images_root=images_root,
        config=None,
        no_pretrained_backbone=True,
        **extra,
    )


def test_grad_clip_flag_reaches_the_config(tmp_path):
    """--grad-clip must override the 0.5 hard default in the full-run config.

    Regression: the flag did not exist, so ``grad_clip`` was unreachable from the
    CLI even though it is the value the pilot exists to choose. Measured pre-clip
    norms on this model run 65-120, so the 0.5 default truncates every step by
    roughly 130x and the clip, not the LR schedule, sets the step size.
    """
    cfg = build_config(_grad_clip_args(tmp_path, grad_clip=96.0))
    assert cfg["grad_clip"] == 96.0


def test_grad_clip_defaults_to_the_hard_default_when_unset(tmp_path):
    cfg = build_config(_grad_clip_args(tmp_path, grad_clip=None))
    assert cfg["grad_clip"] == _HARD_DEFAULTS["grad_clip"]


def test_grad_clip_zero_survives_the_merge_as_zero(tmp_path):
    """0 means "disable clipping"; it must not fall back to 0.5 via truthiness."""
    cfg = build_config(_grad_clip_args(tmp_path, grad_clip=0.0))
    assert cfg["grad_clip"] == 0.0


def test_grad_clip_flag_is_exposed_on_the_parser():
    args = _build_parser().parse_args(["--grad-clip", "96"])
    assert args.grad_clip == 96.0
    assert _build_parser().parse_args([]).grad_clip is None
