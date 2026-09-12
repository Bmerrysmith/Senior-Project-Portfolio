"""Unified ``agrinav`` command-line entry point.

A thin dispatcher: each subcommand forwards its remaining arguments to the
existing ``main()`` of the corresponding module (which owns its own argparse).
This keeps a single discoverable entry point without duplicating any tool logic.

    agrinav --help
    agrinav data-validate --help
    agrinav pretrain --self-test

Every module is also runnable directly, e.g.
``python -m agrinav.training.riceseg_pretrain --self-test``.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from collections.abc import Sequence

import agrinav

# Command name -> fully-qualified module providing a `main()`.
COMMANDS: dict[str, str] = {
    # --- data / annotation tooling ---
    "data-split": "agrinav.data.build_detector_split",
    "data-validate": "agrinav.data.validate_annotation_package",
    "data-export-yolo": "agrinav.data.export_yolo_dataset",
    "data-riceseg-to-coco": "agrinav.data.riceseg_masks_to_coco",
    "data-paddy-to-coco": "agrinav.data.paddy_supervisely_to_coco",
    "data-coco-to-proposals": "agrinav.data.coco_boxes_to_proposals",
    "data-locateanything": "agrinav.data.locateanything_to_proposals",
    "data-sam-mask": "agrinav.data.sam_box_to_mask",
    "data-triage": "agrinav.data.triage_proposals",
    "data-pilot": "agrinav.data.build_annotation_pilot",
    "data-anchor-audit": "agrinav.data.anchor_audit",
    "data-build-rice-phase2": "agrinav.data.build_rice_phase2",
    # --- training ---
    "pretrain": "agrinav.training.riceseg_pretrain",
    "baseline-seg": "agrinav.training.baseline_seg_control",
    "baseline-detector": "agrinav.training.baseline_det_control",
    "train-detector": "agrinav.training.weeddet_train",
    # --- evaluation ---
    "evaluate": "agrinav.evaluation.metrics",
    "evaluate-detector": "agrinav.evaluation.runner",
}


def _print_help() -> None:
    print(f"agrinav {agrinav.__version__} - rice/weed perception research CLI\n")
    print("usage: agrinav <command> [args...]\n")
    print("Run 'agrinav <command> --help' for command-specific options.\n")
    print("commands:")
    width = max(len(name) for name in COMMANDS)
    for name, target in COMMANDS.items():
        print(f"  {name:<{width}}  -> {target}")


def _invoke(module_path: str, rest: list[str]) -> int:
    """Dispatch to ``module.main``, forwarding args however that main accepts them."""
    module = importlib.import_module(module_path)
    main = module.main
    if len(inspect.signature(main).parameters) >= 1:
        result = main(rest)
    else:
        # e.g. riceseg_pretrain.main() reads sys.argv directly.
        saved = sys.argv
        sys.argv = [module_path, *rest]
        try:
            result = main()
        finally:
            sys.argv = saved
    return 0 if result is None else int(result)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return 0
    if args[0] in ("-V", "--version"):
        print(agrinav.__version__)
        return 0

    command, rest = args[0], args[1:]
    if command not in COMMANDS:
        print(f"agrinav: unknown command {command!r}\n", file=sys.stderr)
        _print_help()
        return 2
    return _invoke(COMMANDS[command], rest)


if __name__ == "__main__":
    raise SystemExit(main())
