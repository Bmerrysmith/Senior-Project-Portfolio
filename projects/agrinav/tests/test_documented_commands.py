"""The commands in the docs must be runnable commands.

GATE_STATUS.md tells the next person exactly what to run on the A100 — a box
this repo's dev machine is not. A flag that was renamed, or one that never
existed, surfaces there as a failed run after the GPU has already been booked.
Written after `--num-epochs` (the real flag is `--epochs`) was published in the
pilot instructions and caught by hand.

This checks the flags exist and that argparse accepts the command. It cannot
check that a *path* in a command is real, because those paths are on Drive.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agrinav.training.weeddet_train import _build_parser

DOCS = Path(__file__).resolve().parents[1] / "docs"
_BASH_BLOCK = re.compile(r"```bash\n(.*?)\n```", re.S)
_FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def _documented_train_commands() -> list[tuple[str, str]]:
    """Every fenced bash block in docs/ that invokes the detector trainer."""
    found: list[tuple[str, str]] = []
    for path in sorted(DOCS.rglob("*.md")):
        for block in _BASH_BLOCK.findall(path.read_text(encoding="utf-8")):
            command = " ".join(block.split())
            if "weeddet_train" in command:
                found.append((str(path.relative_to(DOCS)), command))
    return found


def _cases() -> list[tuple[str, str]]:
    cases = _documented_train_commands()
    # A repo with no documented train command is a docs regression in itself,
    # so surface it as a case rather than silently parametrising over nothing.
    return cases or [("<none found>", "")]


@pytest.mark.parametrize(
    ("doc", "command"), _cases(), ids=lambda v: v[:60] if isinstance(v, str) else v
)
def test_documented_train_commands_use_real_flags(doc: str, command: str) -> None:
    assert command, f"no documented weeddet_train command found under {DOCS}"

    parser = _build_parser()
    known = {opt for action in parser._actions for opt in action.option_strings}
    unknown = sorted({f for f in _FLAG.findall(command) if f not in known})
    assert not unknown, f"{doc} documents flags the trainer does not accept: {unknown}"


@pytest.mark.parametrize(
    ("doc", "command"), _cases(), ids=lambda v: v[:60] if isinstance(v, str) else v
)
def test_documented_train_commands_parse(doc: str, command: str) -> None:
    assert command, f"no documented weeddet_train command found under {DOCS}"

    argv = command.split()
    # Drop `python -m agrinav.training.weeddet_train`, keep the arguments.
    argv = argv[argv.index("-m") + 2 :] if "-m" in argv else argv[1:]
    # Raises SystemExit on an unknown flag or a bad choice/type.
    _build_parser().parse_args(argv)
