"""Read a run's ``metrics.jsonl`` and answer the questions the 2-epoch pilot exists to settle.

The pilot (``docs/GATE_STATUS.md``) is run to decide four things before another
18-epoch run is booked:

1. What ``grad_clip`` should be, or whether it should be dropped. The 2026-07-30
   run clipped 3150 of 3150 steps at 0.5, so the clip and not the LR schedule set
   the step size — and only the count survived, not the distribution.
2. Whether the train/eval BatchNorm gap is opening, and from which epoch.
3. Whether the classifier is learning objects or only learning to say
   "background" — a falling total hides this.
4. Whether the BN freeze actually held, as observed state rather than as the
   value that was requested.

This module only reads what the trainer already wrote. It computes no metric of
its own and never loads a model, so it is cheap, importable from a notebook, and
testable without a GPU.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ArmReadout",
    "GradClipAdvice",
    "format_report",
    "read_metrics",
    "recommend_grad_clip",
    "summarise_arm",
]

# A clip that binds on this fraction of steps or more is setting the step size,
# not bounding outliers. 0.5 is deliberately loose: the observed failure was
# 1.00, and anything above half the steps already means the schedule is not in
# control. Not a tuned constant — it is the threshold for printing a warning.
BINDING_CLIP_FRACTION = 0.5

# A clip that essentially never fires is doing nothing but costing a norm
# computation; below this it is reported as droppable.
INERT_CLIP_FRACTION = 0.01

# train/eval peak-confidence ratio outside [1/x, x] is treated as a real gap.
# The observed failure was ~47x (0.9367 under batch stats vs ~0.02 under running
# stats); 3.0 is the provisional bound also used by the overfit gate.
PARITY_RATIO_BOUND = 3.0


@dataclass(frozen=True)
class GradClipAdvice:
    """What the observed gradient-norm distribution says about ``grad_clip``."""

    threshold_used: float | None
    max_clipped_fraction: float | None
    worst_p99: float | None
    recommended: float | None
    verdict: str


@dataclass(frozen=True)
class ArmReadout:
    """One arm of the pilot, summarised from its ``metrics.jsonl``."""

    name: str
    epochs: int
    grad_clip: GradClipAdvice
    parity_ratios: list[float] = field(default_factory=list)
    cls_pos: list[float] = field(default_factory=list)
    cls_neg: list[float] = field(default_factory=list)
    bn_observed: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def read_metrics(path: str | Path) -> list[dict[str, Any]]:
    """Parse a ``metrics.jsonl`` into a list of row dicts.

    A trailing partial line is skipped rather than raised on: the file is
    appended to during training, and a pilot is often read while the second arm
    is still running. Any *earlier* malformed line is a real corruption and
    raises, because silently dropping a mid-file row would understate the
    epoch count the rest of this module reasons about.
    """
    p = Path(path)
    if p.is_dir():
        p = p / "metrics.jsonl"
    if not p.exists():
        raise FileNotFoundError(
            f"no metrics.jsonl at {p}. Point this at the run directory "
            "(--checkpoint-dir) of a run that completed at least one epoch."
        )

    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break  # torn final append; training is probably still running
            raise
    return rows


def _series(rows: list[dict[str, Any]], key: str) -> list[float]:
    """Numeric values for ``key``, skipping missing and non-finite entries.

    NaN passes ``isinstance(x, float)``, so an unfiltered series lets a single
    AMP-overflow epoch turn ``max(...)`` into NaN -- and whether it does is
    decided by list order, which is how one pilot arm recommended a real
    grad_clip and the other recommended ``nan`` from the same code path.
    """
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = float(value)
            if math.isfinite(value):
                values.append(value)
    return values


def recommend_grad_clip(rows: list[dict[str, Any]]) -> GradClipAdvice:
    """Turn the recorded gradient-norm distribution into a concrete recommendation.

    The rule is deliberately simple and stated in the verdict text, so the
    number can be argued with: clip at the worst per-epoch p99, so roughly the
    top 1% of steps are bounded and the schedule controls the rest.
    """
    fractions = _series(rows, "grad_norm/clipped_fraction")
    p99s = _series(rows, "grad_norm/p99")
    thresholds = _series(rows, "grad_norm/clip_threshold")

    threshold = thresholds[-1] if thresholds else None
    worst_fraction = max(fractions) if fractions else None
    worst_p99 = max(p99s) if p99s else None

    if worst_fraction is None or worst_p99 is None:
        return GradClipAdvice(
            threshold_used=threshold,
            max_clipped_fraction=worst_fraction,
            worst_p99=worst_p99,
            recommended=None,
            verdict=(
                "no gradient-norm rows found. Was this run produced by a build "
                "that records grad_norm/*? Re-run the pilot on the pinned commit."
            ),
        )

    # Round to two significant-ish figures so the recommendation reads as a
    # setting rather than as a spuriously precise measurement.
    recommended = round(worst_p99, 2)

    if worst_fraction >= BINDING_CLIP_FRACTION:
        verdict = (
            f"the clip is BINDING: it fired on {worst_fraction:.1%} of steps at "
            f"{threshold}. The clip, not the LR schedule, set the step size. "
            f"Raise grad_clip to about {recommended} (the worst epoch's p99), or "
            "drop it and let the schedule control the step."
        )
    elif worst_fraction <= INERT_CLIP_FRACTION:
        verdict = (
            f"the clip is INERT: it fired on {worst_fraction:.1%} of steps at "
            f"{threshold}. It is bounding outliers only, which is what a clip is "
            f"for. Keep it, or drop it as dead weight; observed p99 is {worst_p99:.3f}."
        )
    else:
        verdict = (
            f"the clip fired on {worst_fraction:.1%} of steps at {threshold}, "
            f"against an observed p99 of {worst_p99:.3f}. It is doing real work "
            f"without dominating. {recommended} would bound roughly the top 1%."
        )

    return GradClipAdvice(
        threshold_used=threshold,
        max_clipped_fraction=worst_fraction,
        worst_p99=worst_p99,
        recommended=recommended,
        verdict=verdict,
    )


def summarise_arm(path: str | Path, name: str | None = None) -> ArmReadout:
    """Summarise one pilot arm from its run directory or ``metrics.jsonl``."""
    rows = read_metrics(path)
    label = name or Path(path).name

    ratios = _series(rows, "parity/max_conf_ratio")
    cls_pos = _series(rows, "train/cls_loss_pos")
    cls_neg = _series(rows, "train/cls_loss_neg")

    bn_keys = (
        "bn/total",
        "bn/eval_mode",
        "bn/grad_off",
        "bn/backbone_total",
        "bn/backbone_eval_mode",
    )
    bn_observed = {k: rows[-1][k] for k in bn_keys if rows and k in rows[-1]}

    warnings: list[str] = []

    if not rows:
        warnings.append("metrics.jsonl is empty: the run recorded no completed epoch.")

    bad_parity = [
        (i + 1, r)
        for i, r in enumerate(ratios)
        if not (1.0 / PARITY_RATIO_BOUND <= r <= PARITY_RATIO_BOUND)
    ]
    if bad_parity:
        first_epoch, first_ratio = bad_parity[0]
        warnings.append(
            f"train/eval BN confidence gap opens at epoch {first_epoch} "
            f"(ratio {first_ratio:.2f}, outside "
            f"[{1 / PARITY_RATIO_BOUND:.2f}, {PARITY_RATIO_BOUND:.2f}]). The "
            "remaining trainable head BN is the first place to look; "
            "GroupNorm there is the ablation."
        )
    elif len(ratios) >= 2 and ratios[-1] > ratios[0] * 1.5:
        warnings.append(
            f"train/eval ratio is widening ({ratios[0]:.2f} -> {ratios[-1]:.2f}) "
            "while still inside bounds. Two epochs may be too few to see where "
            "it lands; watch it rather than clearing it."
        )

    # The failure a falling total hides: negatives improve, positives do not.
    if len(cls_pos) >= 2 and cls_pos[-1] >= cls_pos[0] and cls_neg[-1] < cls_neg[0]:
        warnings.append(
            f"cls_loss_pos did not fall ({cls_pos[0]:.4f} -> {cls_pos[-1]:.4f}) "
            f"while cls_loss_neg did ({cls_neg[0]:.4f} -> {cls_neg[-1]:.4f}). "
            "The classifier is learning to say 'background', not to find objects. "
            "A falling total loss would have hidden this."
        )

    if bn_observed:
        total = bn_observed.get("bn/total")
        frozen = bn_observed.get("bn/eval_mode")
        if isinstance(total, int) and isinstance(frozen, int) and frozen == 0 and total:
            warnings.append(
                f"0 of {total} BN layers were observed in eval mode: the freeze "
                "did not hold, whatever --bn-policy requested."
            )

    return ArmReadout(
        name=label,
        epochs=len(rows),
        grad_clip=recommend_grad_clip(rows),
        parity_ratios=ratios,
        cls_pos=cls_pos,
        cls_neg=cls_neg,
        bn_observed=bn_observed,
        warnings=warnings,
    )


def _fmt_series(values: list[float], fmt: str = "{:.4f}") -> str:
    return " -> ".join(fmt.format(v) for v in values) if values else "(none recorded)"


def format_report(arms: list[ArmReadout]) -> str:
    """Human-readable readout: one section per arm, then the decisions."""
    out: list[str] = []
    for arm in arms:
        out.append(f"=== {arm.name} — {arm.epochs} epoch(s) recorded ===")
        out.append(f"  grad_norm    : {arm.grad_clip.verdict}")
        out.append(f"  parity ratio : {_fmt_series(arm.parity_ratios, '{:.2f}')}")
        out.append(f"  cls_loss_pos : {_fmt_series(arm.cls_pos)}")
        out.append(f"  cls_loss_neg : {_fmt_series(arm.cls_neg)}")
        if arm.bn_observed:
            bn = ", ".join(f"{k.split('/', 1)[1]}={v}" for k, v in arm.bn_observed.items())
            out.append(f"  bn observed  : {bn}")
        for warning in arm.warnings:
            out.append(f"  !! {warning}")
        out.append("")

    out.append("=== decisions ===")
    recommended = [a.grad_clip.recommended for a in arms if a.grad_clip.recommended]
    if recommended:
        out.append(
            f"  grad_clip : set to {max(recommended)} (the larger of the arms' "
            "worst-epoch p99), or drop it — see each arm's verdict above."
        )
    else:
        out.append("  grad_clip : no recommendation; no gradient-norm rows were found.")

    any_parity_warning = any("gap opens" in w or "widening" in w for a in arms for w in a.warnings)
    out.append(
        "  head BN   : "
        + (
            "a train/eval gap is present — run the GroupNorm ablation."
            if any_parity_warning
            else "no train/eval gap in these epochs; GroupNorm is not indicated yet."
        )
    )
    out.append(
        "  full run  : "
        + (
            "NOT yet — resolve the warnings above first."
            if any(a.warnings for a in arms)
            else "the four pilot readings are clean; the 18-epoch run is unblocked."
        )
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """``python -m agrinav.training.pilot_report RUN_DIR [RUN_DIR ...]``."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m agrinav.training.pilot_report",
        description=(
            "Read the 2-epoch pilot's metrics.jsonl and report what it settles: "
            "grad_clip, the train/eval BN gap, the positive/negative loss split, "
            "and whether the BN freeze held."
        ),
    )
    parser.add_argument(
        "run_dirs",
        nargs="+",
        metavar="RUN_DIR",
        help="run directory (--checkpoint-dir) or a metrics.jsonl path, one per arm",
    )
    args = parser.parse_args(argv)

    arms = [summarise_arm(d) for d in args.run_dirs]
    print(format_report(arms))
    # Exit non-zero when any arm raised a warning, so a notebook cell with
    # check=True stops rather than printing a problem and sailing on.
    return 1 if any(a.warnings for a in arms) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
