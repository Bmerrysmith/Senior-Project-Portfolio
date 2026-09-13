"""Tests for the baseline control's pure helpers.

Deliberately network-free and CPU-only: build_model() downloads pretrained
weights, so it is exercised on Colab, not here. What IS tested here is the
reporting logic that decides the experiment's conclusion — if stability_stats
is wrong, the wrong architecture decision gets made.
"""

from __future__ import annotations

import pytest

from agrinav.training.baseline_seg_control import ARCHS, build_model, stability_stats


def _hist(mious, weeds=None, n_from=1):
    """Build a minimal history list like the training loop emits."""
    out = []
    for i, m in enumerate(mious):
        w = weeds[i] if weeds is not None else m
        out.append(
            {
                "epoch": n_from + i,
                "loss": 1.0,
                "miou": m,
                "per_class_iou": {
                    "background": 0.9,
                    "green_veg": 0.9,
                    "senescent": 0.3,
                    "panicle": 0.7,
                    "weeds": w,
                    "duckweed": 0.3,
                },
                "absent_classes": [],
            }
        )
    return out


def test_empty_history_returns_empty():
    assert stability_stats([]) == {}


def test_window_takes_the_last_n_epochs():
    s = stability_stats(_hist([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]), window=3)
    assert s["window"] == 3
    assert s["epochs"] == [4, 5, 6]
    assert s["miou_mean"] == pytest.approx(0.5)


def test_window_larger_than_history_is_clamped():
    s = stability_stats(_hist([0.4, 0.6]), window=10)
    assert s["window"] == 2
    assert s["miou_mean"] == pytest.approx(0.5)


def test_std_captures_the_instability_that_motivates_this_run():
    """The real weeds series swung 0.11-0.34 while loss fell smoothly. A high
    std must survive into the report, otherwise a noisy peak reads as a win."""
    noisy = _hist([0.55] * 6, weeds=[0.29, 0.25, 0.34, 0.27, 0.12, 0.19])
    s = stability_stats(noisy, window=6)
    w = s["per_class"]["weeds"]
    assert w["min"] == pytest.approx(0.12)
    assert w["max"] == pytest.approx(0.34)
    assert w["std"] > 0.06, "instability must not be smoothed away"
    assert w["mean"] == pytest.approx(0.24333, abs=1e-4)


def test_absent_class_is_skipped_not_counted_as_zero():
    """A class absent from an epoch is None. Counting it as 0.0 would fabricate
    a low score for a class that simply did not appear."""
    h = _hist([0.5, 0.5, 0.5])
    h[1]["per_class_iou"]["duckweed"] = None
    s = stability_stats(h, window=3)
    d = s["per_class"]["duckweed"]
    assert d["n"] == 2
    assert d["mean"] == pytest.approx(0.3)


def test_all_absent_class_reports_none_not_nan():
    h = _hist([0.5, 0.5])
    for e in h:
        e["per_class_iou"]["duckweed"] = None
    d = stability_stats(h, window=2)["per_class"]["duckweed"]
    assert d["n"] == 0
    assert d["mean"] is None and d["std"] is None


def test_every_class_is_reported_even_when_never_present():
    s = stability_stats(_hist([0.5]), window=1)
    assert set(s["per_class"]) == {
        "background",
        "green_veg",
        "senescent",
        "panicle",
        "weeds",
        "duckweed",
    }


def test_unknown_arch_is_rejected():
    with pytest.raises(SystemExit):
        build_model("resnet18_unet")


def test_arch_list_is_what_the_cli_advertises():
    assert ARCHS == ("deeplabv3_resnet50", "segformer_b2")


def test_segformer_scratch_is_refused_rather_than_silently_pretrained():
    """--no-pretrained is only implemented for deeplab; it must fail loudly
    instead of quietly returning an ADE20K-pretrained SegFormer."""
    with pytest.raises(SystemExit):
        build_model("segformer_b2", pretrained=False)
