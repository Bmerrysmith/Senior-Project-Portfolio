# ADR 0002: pyproject packaging, tooling, and fast CI

## Status

Accepted — 2026-07-22

## Context

The project had only an unpinned `requirements.txt` and a single Qodana workflow
— no `pyproject.toml`, no linting/formatting/type-checking config, no pre-commit,
and no fast test CI. Roadmap Gate 1 (§7 of the deployment roadmap) requires ruff,
mypy, pytest, pre-commit, and CPU CI before further experiments.

## Decision

- **Packaging:** `pyproject.toml` is the single source of truth (setuptools
  backend, `src` layout). `requirements.txt` is reduced to a pointer that installs
  `-e .[train]` (kept so Colab's `pip install -r requirements.txt` still works).
- **Dependency groups:** base = data-tooling (numpy, Pillow, OpenCV, pycocotools,
  shapely, …); extras `train` (torch, torchvision, transformers), `inference`
  (torch, torchvision), `docs` (mkdocs), and `dev` (`agrinav[train]` + tooling).
- **torch/torchvision are pinned as ranges, not exact versions.** The concrete
  wheel is CPU/CUDA- and platform-specific and is selected per environment
  (roadmap Gate-1 item 5); CI installs the CPU wheels from the PyTorch CPU index.
  A fully hash-locked lockfile is deferred until the supported torch/CUDA matrix
  is defined.
- **Formatting/lint split:** Ruff owns linting + import sorting; Black is the sole
  formatter (Ruff's formatter is intentionally not used, to avoid two formatters
  disagreeing).
- **Ruff rule set is conservative** (`E4/E7/E9/F/W/I`) to start green; stricter
  families (`B`, `UP`, `SIM`, `PTH`) are enabled later.
- **`weeddet_v6b.py` is excluded from Ruff and Black** and held byte-stable: the
  July-20 audit references its exact line numbers and Gate-4 correctness work is
  still open. It is reformatted only when that rewrite lands.
- **mypy is non-blocking** in CI initially (legacy ML modules are typed
  incrementally; third-party libs often ship no stubs).
- **CI (`.github/workflows/ci.yml`):** `lint` (ruff + black --check), `typecheck`
  (mypy, non-blocking), `test` (pytest on CPU, Python 3.11 + 3.12), and `package`
  (build + `twine check`). Least-privilege permissions, timeouts, pip caching.
  The existing Qodana workflow is retained (complementary).

## Alternatives considered

- **Exact-pin every dependency including torch.** Rejected for torch: exact pins
  fight the CPU/CUDA wheel selection. Ranges + per-environment resolution is the
  standard torch practice; §7 of the roadmap endorses a lock file for exact
  reproducibility, deferred here.
- **Enforce Black across `weeddet_v6b.py` now.** Rejected: it would churn a
  correctness-sensitive file and desync the audit's line references.
- **Use `uv`/`ruff format` as the formatter.** Not available in the current
  environment; Black is the project's stated canonical formatter.

## Consequences

- Green, reproducible dev tooling: `pip install -e ".[dev]"`, `make lint`,
  `make test`, `pre-commit run --all-files`.
- Two follow-ups tracked: (1) a committed lockfile once the torch/CUDA matrix is
  fixed; (2) enabling stricter ruff rules and blocking mypy, including formatting
  `weeddet_v6b.py`, during the Gate-4 detector rewrite.

## References

- `docs/audits/2026-07-20/AGRINAV_DEPLOYMENT_ROADMAP_2026-07-20.md` §7 (Gate 1)
- ADR 0001 (src layout)
