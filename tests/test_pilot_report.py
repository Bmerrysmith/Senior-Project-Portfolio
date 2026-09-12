"""The pilot readout must reach the right verdict, including the ones that hurt.

Every fixture here encodes an observed or specifically-feared failure, not a
generic happy path: the clip that fired on every step, the BN gap that opened
mid-run, and the classifier that learned "background" while the total loss fell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agrinav.training.pilot_report import (
    BINDING_CLIP_FRACTION,
    ArmReadout,
    format_report,
    main,
    read_metrics,
    recommend_grad_clip,
    summarise_arm,
)


def _write(tmp_path: Path, rows: list[dict], name: str = "run") -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return run_dir


def _row(epoch: int, **over: float) -> dict:
    row = {
        "epoch": epoch,
        "train/total_loss": 1.0 / epoch,
        "train/cls_loss_pos": 0.5 / epoch,
        "train/cls_loss_neg": 0.4 / epoch,
        "grad_norm/p50": 0.10,
        "grad_norm/p99": 0.40,
        "grad_norm/max": 0.60,
        "grad_norm/clipped_fraction": 0.02,
        "grad_norm/clip_threshold": 0.5,
        "parity/max_conf_ratio": 1.05,
        "bn/total": 58,
        "bn/eval_mode": 57,
        "bn/grad_off": 57,
    }
    row.update(over)
    return row


# --- reading -----------------------------------------------------------------


def test_a_torn_final_line_is_tolerated_because_the_arm_may_still_be_running(
    tmp_path: Path,
) -> None:
    run_dir = _write(tmp_path, [_row(1), _row(2)])
    with (run_dir / "metrics.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"epoch": 3, "train/tot')

    assert len(read_metrics(run_dir)) == 2


def test_a_corrupt_middle_line_is_not_silently_dropped(tmp_path: Path) -> None:
    run_dir = _write(tmp_path, [_row(1), _row(2)])
    path = run_dir / "metrics.jsonl"
    path.write_text('{"epoch": 1}\nNOT JSON\n{"epoch": 3}\n', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        read_metrics(run_dir)


def test_a_missing_file_names_the_flag_that_produces_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="checkpoint-dir"):
        read_metrics(tmp_path / "nope")


def test_a_metrics_jsonl_path_works_as_well_as_a_run_dir(tmp_path: Path) -> None:
    run_dir = _write(tmp_path, [_row(1)])
    assert read_metrics(run_dir / "metrics.jsonl") == read_metrics(run_dir)


# --- grad_clip ---------------------------------------------------------------


def test_a_clip_that_fires_every_step_is_called_binding() -> None:
    rows = [_row(e, **{"grad_norm/clipped_fraction": 1.0, "grad_norm/p99": 3.2}) for e in (1, 2)]

    advice = recommend_grad_clip(rows)

    assert "BINDING" in advice.verdict
    assert advice.recommended == pytest.approx(3.2)
    assert advice.max_clipped_fraction == pytest.approx(1.0)


def test_the_recommendation_comes_from_the_worst_epoch_not_the_last() -> None:
    rows = [
        _row(1, **{"grad_norm/p99": 9.0, "grad_norm/clipped_fraction": 1.0}),
        _row(2, **{"grad_norm/p99": 0.2, "grad_norm/clipped_fraction": 1.0}),
    ]

    assert recommend_grad_clip(rows).recommended == pytest.approx(9.0)


def test_a_clip_that_never_fires_is_called_inert() -> None:
    rows = [_row(e, **{"grad_norm/clipped_fraction": 0.0}) for e in (1, 2)]

    assert "INERT" in recommend_grad_clip(rows).verdict


def test_a_clip_doing_real_work_is_neither_binding_nor_inert() -> None:
    rows = [_row(e, **{"grad_norm/clipped_fraction": 0.10}) for e in (1, 2)]
    verdict = recommend_grad_clip(rows).verdict

    assert "BINDING" not in verdict and "INERT" not in verdict


def test_the_binding_threshold_is_the_boundary_it_claims_to_be() -> None:
    just_over = [_row(1, **{"grad_norm/clipped_fraction": BINDING_CLIP_FRACTION + 0.01})]
    just_under = [_row(1, **{"grad_norm/clipped_fraction": BINDING_CLIP_FRACTION - 0.01})]

    assert "BINDING" in recommend_grad_clip(just_over).verdict
    assert "BINDING" not in recommend_grad_clip(just_under).verdict


def test_a_run_without_gradient_rows_says_so_instead_of_recommending_a_number() -> None:
    advice = recommend_grad_clip([{"epoch": 1, "train/total_loss": 1.0}])

    assert advice.recommended is None
    assert "no gradient-norm rows" in advice.verdict


# --- BN parity ---------------------------------------------------------------


def test_a_clean_arm_raises_no_warning(tmp_path: Path) -> None:
    arm = summarise_arm(_write(tmp_path, [_row(1), _row(2)]))

    assert arm.warnings == []
    assert arm.epochs == 2


def test_an_opened_bn_gap_is_reported_with_the_epoch_it_opened(tmp_path: Path) -> None:
    rows = [_row(1), _row(2, **{"parity/max_conf_ratio": 47.0})]

    arm = summarise_arm(_write(tmp_path, rows))

    assert any("gap opens at epoch 2" in w for w in arm.warnings)
    assert any("GroupNorm" in w for w in arm.warnings)


def test_an_inverted_gap_counts_too_because_the_bound_is_two_sided(tmp_path: Path) -> None:
    rows = [_row(1, **{"parity/max_conf_ratio": 0.02})]

    assert any("gap opens" in w for w in summarise_arm(_write(tmp_path, rows)).warnings)


def test_a_widening_but_in_bounds_ratio_is_flagged_as_watch_not_as_pass(
    tmp_path: Path,
) -> None:
    rows = [_row(1, **{"parity/max_conf_ratio": 1.0}), _row(2, **{"parity/max_conf_ratio": 2.0})]

    assert any("widening" in w for w in summarise_arm(_write(tmp_path, rows)).warnings)


# --- the failure a falling total hides ---------------------------------------


def test_a_classifier_learning_only_background_is_caught(tmp_path: Path) -> None:
    # Total loss falls every epoch, which the old gate would have accepted.
    rows = [
        _row(
            1, **{"train/cls_loss_pos": 0.50, "train/cls_loss_neg": 0.90, "train/total_loss": 1.40}
        ),
        _row(
            2, **{"train/cls_loss_pos": 0.52, "train/cls_loss_neg": 0.30, "train/total_loss": 0.82}
        ),
    ]

    arm = summarise_arm(_write(tmp_path, rows))

    assert any("learning to say 'background'" in w for w in arm.warnings)
    assert rows[1]["train/total_loss"] < rows[0]["train/total_loss"]


def test_both_halves_falling_is_not_flagged(tmp_path: Path) -> None:
    rows = [
        _row(1, **{"train/cls_loss_pos": 0.50, "train/cls_loss_neg": 0.90}),
        _row(2, **{"train/cls_loss_pos": 0.30, "train/cls_loss_neg": 0.40}),
    ]

    arm = summarise_arm(_write(tmp_path, rows))

    assert not any("background" in w for w in arm.warnings)


# --- observed BN state -------------------------------------------------------


def test_a_freeze_that_did_not_hold_is_reported(tmp_path: Path) -> None:
    rows = [_row(1, **{"bn/eval_mode": 0, "bn/grad_off": 0})]

    arm = summarise_arm(_write(tmp_path, rows))

    assert any("0 of 58" in w and "did not hold" in w for w in arm.warnings)


def test_observed_bn_counts_are_carried_through(tmp_path: Path) -> None:
    arm = summarise_arm(_write(tmp_path, [_row(1)]))

    assert arm.bn_observed["bn/eval_mode"] == 57
    assert arm.bn_observed["bn/total"] == 58


def test_an_empty_metrics_file_is_a_warning_not_a_crash(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    (run_dir / "metrics.jsonl").write_text("", encoding="utf-8")

    arm = summarise_arm(run_dir)

    assert arm.epochs == 0
    assert any("no completed epoch" in w for w in arm.warnings)


# --- report and CLI ----------------------------------------------------------


def test_the_report_recommends_the_larger_clip_across_both_arms() -> None:
    arms = [
        ArmReadout(
            name="a",
            epochs=2,
            grad_clip=recommend_grad_clip(
                [_row(1, **{"grad_norm/p99": 1.5, "grad_norm/clipped_fraction": 1.0})]
            ),
        ),
        ArmReadout(
            name="b",
            epochs=2,
            grad_clip=recommend_grad_clip(
                [_row(1, **{"grad_norm/p99": 4.0, "grad_norm/clipped_fraction": 1.0})]
            ),
        ),
    ]

    assert "set to 4.0" in format_report(arms)


def test_a_clean_pair_of_arms_unblocks_the_full_run(tmp_path: Path) -> None:
    arms = [summarise_arm(_write(tmp_path, [_row(1), _row(2)], name)) for name in ("a", "b")]

    report = format_report(arms)

    assert "18-epoch run is unblocked" in report
    assert "GroupNorm is not indicated yet" in report


def test_a_dirty_arm_blocks_the_full_run(tmp_path: Path) -> None:
    dirty = _write(tmp_path, [_row(1), _row(2, **{"parity/max_conf_ratio": 47.0})], "dirty")

    report = format_report([summarise_arm(dirty)])

    assert "NOT yet" in report
    assert "run the GroupNorm ablation" in report


def test_the_cli_exit_code_is_the_gate(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    clean = _write(tmp_path, [_row(1), _row(2)], "clean")
    dirty = _write(tmp_path, [_row(1, **{"parity/max_conf_ratio": 47.0})], "dirty")

    assert main([str(clean)]) == 0
    assert main([str(dirty)]) == 1
    assert "parity ratio" in capsys.readouterr().out


def test_the_cli_reads_both_arms_in_one_invocation(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    a = _write(tmp_path, [_row(1), _row(2)], "pilot_riceseg")
    b = _write(tmp_path, [_row(1), _row(2)], "pilot_imagenet")

    main([str(a), str(b)])
    out = capsys.readouterr().out

    assert "pilot_riceseg" in out and "pilot_imagenet" in out


def test_series_skips_non_finite_so_a_nan_epoch_cannot_poison_the_advice():
    """One AMP-overflow epoch must not turn the grad_clip advice into NaN.

    Regression from the 2026-08-19 pilot: the ImageNet arm recommended `nan`
    while the RiceSEG arm recommended 12.74 from the same code path. NaN passes
    `isinstance(x, float)`, so it reached `max(...)`, where the result depends on
    list order.
    """
    from agrinav.training.pilot_report import _series, recommend_grad_clip

    rows = [
        {"grad_norm/p99": float("nan"), "grad_norm/clipped_fraction": 1.0,
         "grad_norm/clip_threshold": 0.5},
        {"grad_norm/p99": 12.74, "grad_norm/clipped_fraction": 1.0,
         "grad_norm/clip_threshold": 0.5},
    ]
    assert _series(rows, "grad_norm/p99") == [12.74]

    advice = recommend_grad_clip(rows)
    assert advice.worst_p99 == 12.74
    assert "nan" not in advice.verdict.lower()


def test_series_skips_non_finite_regardless_of_order():
    from agrinav.training.pilot_report import _series

    for tail in (float("inf"), float("-inf"), float("nan")):
        assert _series([{"k": 3.0}, {"k": tail}], "k") == [3.0]
        assert _series([{"k": tail}, {"k": 3.0}], "k") == [3.0]
