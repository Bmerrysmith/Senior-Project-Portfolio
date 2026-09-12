# ADR 0001: Adopt a `src/agrinav` package layout

## Status

Accepted — 2026-07-22

## Context

Production logic lived in flat top-level directories (`models/`, `training/`,
`scripts/`, `data/`, `inference/`) with no installable package. Tests and modules
relied on the repository root being on `sys.path`, and two modules used
`sys.path.insert(...)` hacks to import siblings. This is exactly the
"notebook/Colab-state, hand-copied module" reproducibility gap called out in the
July-20 deployment roadmap (Gate 1, §5), which prescribes a `src/agrinav` layout
where "Python modules are the source of truth; notebooks import them."

## Decision

Adopt a `src/` layout with a single import package, `agrinav`:

```
src/agrinav/
├── __init__.py          # __version__
├── cli.py               # unified `agrinav` entry point
├── models/              # weeddet_v6b (held byte-stable; see ADR 0002)
├── training/            # riceseg_pretrain, baseline_seg_control
├── data/                # annotation + dataset tooling (former scripts/)
└── inference/           # disabled/safe-stub runtime notes
```

All modules moved with `git mv` (history preserved). Imports were rewritten to
absolute `agrinav.*` paths and the two `sys.path.insert` hacks were removed. The
top-level `data/` directory is retained as a **data-artifacts** directory
(manifests, schemas) and is no longer a Python package.

## Alternatives considered

- **Keep the flat layout, add packaging around it.** Rejected: preserves the
  `sys.path` fragility and does not match the roadmap's target structure.
- **Also split the monolithic `weeddet_v6b.py` now.** Deferred to Gate 4: that
  file has open correctness work and the audit references its exact line numbers.

## Consequences

- `pip install -e .` yields a real, importable package; notebooks/CLIs no longer
  depend on the working directory or Colab paths.
- One-time import churn across the moved modules and all test files.
- Follow-up: consolidate the many `data-*` CLI verbs into the roadmap's
  higher-level command groups as the data pipeline stabilises.

## References

- `docs/audits/2026-07-20/AGRINAV_DEPLOYMENT_ROADMAP_2026-07-20.md` §5–6 (Gate 1)
- ADR 0002 (packaging, tooling, CI)
