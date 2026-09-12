# GitHub / CI Architecture Plan

> How to organize EagleGIS's repository and all of its pipelines for maximum
> efficiency, based on the current repo state and 2026 GitHub Actions / Python
> monorepo best practices.
>
> **Assumed decisions** (recommended defaults — change any and the plan adapts):
> 1. **Restructure the existing repo in place** (keep git history, the working
>    workflows, GH Pages, and the Supabase secrets + Cloud Run WIF already set up).
> 2. **Monorepo** — API + data pipeline + `rag-service` + shared models in one repo.
> 3. **Adopt `uv` workspaces + dependency groups**, migrated in safe phases.

## Current state (facts, audited)

Six workflows in `.github/workflows/`:

| Workflow | Trigger | Job(s) |
| --- | --- | --- |
| `ci.yml` | push/PR to main | `test` (pytest), `pipeline` (strict build + silver/gold up-to-date guard), `api-health` (gated on `vars.RUN_API_HEALTH`) |
| `publish.yml` | push (path-filtered) + nightly + dispatch | publish + verify to Supabase |
| `refresh-data.yml` | weekly + dispatch | scrape, rebuild, commit artifacts, publish + verify |
| `drift-watch.yml` | every 6h + dispatch | verify (read-only) |
| `discover-meetings.yml` | monthly + dispatch | scrape, open PR if new candidates |
| `deploy-cloud-run.yml` | push (path-filtered `rag_service/**`) + dispatch | build + push + deploy RAG service via WIF |

Every job repeats `checkout` -> `setup-python@v5 (cache: pip)` -> `pip install -r requirements.txt`. `publish` / `refresh-data` / `drift-watch` additionally duplicate the manifest-upload + job-summary steps and the Supabase `env` block. Two Python dependency files exist (`requirements.txt`, `rag_service/requirements.txt`).

## The four efficiency problems (and the fix for each)

1. **YAML duplication** -> **composite action** for env setup + **reusable workflows** (`workflow_call`) for shared job bodies.
2. **Dependency bloat** -> the assistant pulls in `torch`/`sentence-transformers` (multi-GB). If that lands in the shared `requirements.txt`, all five data workflows start installing it for nothing. Fix: **dependency layering** (PEP 735 groups) so each job installs only its slice.
3. **No change detection** -> every push runs everything. Fix: **path-aware detection -> dynamic jobs**, with a **gatekeeper** job as the single required status check.
4. **Slow/!reproducible installs** -> **`uv`** (single `uv.lock`, `uv sync --frozen`, 10-100x faster, hermetic).

---

## Target repo layout (uv workspace, in place)

```
EagleGIS/
├── pyproject.toml              # workspace root = the API package ("app"); dependency groups
├── uv.lock                     # single lockfile for the whole workspace
├── app/                        # UNCHANGED location: FastAPI app + data pipeline (import path stays `app.*`)
├── services/
│   └── rag-service/            # moved from rag_service/ (own pyproject, heavy ML deps isolated)
├── packages/
│   └── shared/                 # NEW: shared Pydantic models / config (used by app + rag-service + assistant)
├── db/migrations/
├── docs/
├── index.html / dashboard.html # GH Pages (unchanged)
└── .github/
    ├── actions/
    │   ├── setup-env/          # composite: uv install + sync (kills the repeated 3 steps)
    │   └── manifest-summary/   # composite: upload run manifest + write job summary
    └── workflows/
        ├── _python-checks.yml  # reusable: lint + test for a target
        ├── _pipeline.yml       # reusable: run app.pipeline.run with flags + manifest
        ├── ci.yml              # detect -> matrix -> gate
        ├── data-publish.yml    # thin caller (push + nightly)
        ├── data-refresh.yml    # thin caller (weekly, commits artifacts)
        ├── drift-watch.yml     # thin caller (6h, read-only)
        ├── discover-meetings.yml
        └── deploy-cloud-run.yml
```

> `app/` deliberately stays put so `python -m app.pipeline.run`, `uvicorn app.main:app`, the `Procfile`, and every `from app.* import` keep working untouched. Only `rag_service/` relocates (a contained change to the Docker build context + `cloudbuild.yaml` + deploy workflow + Makefile), and that move is an **optional later phase**.

---

## Dependency architecture (the biggest single win)

Root `pyproject.toml` with **PEP 735 dependency groups** so CI installs only what each job needs:

```toml
[project]
name = "eaglegis"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "pydantic>=2.7.0",
  "python-dotenv>=1.0.0",
  "supabase>=2.0.0",
  "PyYAML>=6.0",
  "pypdf",
  "httpx>=0.27.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff", "pre-commit"]
assistant = ["sentence-transformers>=3.0.0", "sqlglot>=25.0"]   # heavy (torch) — isolated
eval = ["ragas", "datasets", "arize-phoenix", "opentelemetry-sdk"]
```

- Data workflows (`publish`, `refresh`, `drift`, `discover`, pipeline guard): `uv sync --frozen` -> **no torch**.
- Tests: `uv sync --frozen --group dev`.
- Assistant build/eval: `uv sync --frozen --group assistant --group eval`.
- `services/rag-service/` keeps its **own** `pyproject.toml` (torch lives only there, only in its image).

This alone removes a multi-GB install from five scheduled workflows.

---

## Reusable CI building blocks

### Composite action: `.github/actions/setup-env/action.yml`
```yaml
name: Set up Python env (uv)
description: Shared dependency setup. Assumes the repo is already checked out.
inputs:
  args:
    description: Args passed to `uv sync` (e.g. "--frozen --group dev").
    required: false
    default: "--frozen"
runs:
  using: composite
  steps:
    - uses: astral-sh/setup-uv@v6
      with:
        enable-cache: true
    - shell: bash
      run: uv sync ${{ inputs.args }}
```

### Reusable workflow: `.github/workflows/_pipeline.yml`
```yaml
name: Pipeline (reusable)
on:
  workflow_call:
    inputs:
      run-args:      { type: string,  required: true }   # e.g. "--verify --strict"
      manifest-name: { type: string,  default: "manifest" }
    secrets:
      SUPABASE_URL:         { required: false }
      SUPABASE_KEY:         { required: false }
      SUPABASE_SERVICE_KEY: { required: false }
jobs:
  run:
    runs-on: ubuntu-latest
    env:
      SUPABASE_URL:         ${{ secrets.SUPABASE_URL }}
      SUPABASE_KEY:         ${{ secrets.SUPABASE_KEY }}
      SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-env
      - run: uv run python -m app.pipeline.run ${{ inputs.run-args }}
      - uses: ./.github/actions/manifest-summary
        if: always()
        with: { name: "${{ inputs.manifest-name }}" }
```

The three Supabase workflows collapse into thin callers, e.g. `drift-watch.yml`:
```yaml
name: Drift Watch
on:
  schedule: [{ cron: "0 */6 * * *" }]
  workflow_dispatch:
concurrency: { group: drift-watch, cancel-in-progress: true }
jobs:
  verify:
    uses: ./.github/workflows/_pipeline.yml
    with: { run-args: "--verify --strict", manifest-name: "drift-manifest" }
    secrets: inherit
```

### Change-detection + gatekeeper: `ci.yml`
```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request: { branches: [main] }
  workflow_dispatch:
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      api:  ${{ steps.f.outputs.api }}
      data: ${{ steps.f.outputs.data }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 2 }
      - uses: dorny/paths-filter@v3
        id: f
        with:
          filters: |
            api:  ['app/**', 'packages/**', 'pyproject.toml', 'uv.lock']
            data: ['app/data/**', 'app/pipeline/**']

  api-checks:
    needs: detect
    if: needs.detect.outputs.api == 'true'
    uses: ./.github/workflows/_python-checks.yml
    with: { sync-args: "--frozen --group dev" }

  pipeline-guard:
    needs: detect
    if: needs.detect.outputs.data == 'true'
    uses: ./.github/workflows/_pipeline.yml
    with: { run-args: "--strict --live-geocode --verify-pdf-locations --no-geocode-cache-write", manifest-name: "pipeline-manifest" }
    secrets: inherit

  gate:                       # single REQUIRED status check in branch protection
    if: always()
    needs: [api-checks, pipeline-guard]
    runs-on: ubuntu-latest
    steps:
      - run: |
          for r in "${{ needs.api-checks.result }}" "${{ needs.pipeline-guard.result }}"; do
            if [ "$r" = "failure" ] || [ "$r" = "cancelled" ]; then echo "required job $r"; exit 1; fi
          done
          echo "ok"
```

> **Critical gotcha (from the research):** when a path-filtered job is *skipped*, a branch-protection rule that requires that job by name will block the PR forever. The `gate` job (with `if: always()`) is the fix — make **only `gate`** the required check. The silver/gold "up-to-date" guard from today's `ci.yml` moves into the pipeline-guard path.

---

## Security architecture
- **OIDC/WIF** for Cloud Run is already in place (no JSON keys) — keep it; extend the same pattern to any future GCP deploy.
- **Least-privilege `permissions:`** per workflow (most already scope `contents`/`pull-requests`); default the repo to read-only token and opt up where needed.
- **GitHub Environments** for deploys (e.g. `production`) with required reviewers + environment-scoped secrets; Supabase keys live as secrets (Supabase has no OIDC), scoped to the environments that need them.
- **Pin actions** to major tags (already `@v4`/`@v5`); mask any runtime-generated secrets with `::add-mask::`.

## Caching & concurrency
- `astral-sh/setup-uv@v6` with `enable-cache: true` caches the global uv store; cache key derives from `uv.lock` (no poisoning).
- Standardize `concurrency:` groups across all workflows (cancel-in-progress on PR CI; **off** for publish/refresh/discover so data writes aren't interrupted — matches today's intent).
- `fetch-depth: 2` only where change detection needs it.

---

## Phased migration (each phase keeps CI green — "make no mistakes")

| Phase | Change | Risk | Reversible? |
| --- | --- | --- | --- |
| 0 | Add `pyproject.toml` + dependency groups alongside the existing `requirements.txt` (don't delete it yet) | Low | Yes |
| 1 | Add `setup-env` + `manifest-summary` composite actions and `_pipeline.yml`; refactor `publish`/`refresh`/`drift` into thin callers (behavior-preserving) | Low | Yes |
| 2 | Add `detect` + `gate` to `ci.yml`; switch the branch-protection required check to `gate` | Low-Med | Yes |
| 3 | Move assistant/torch deps into the `assistant` group so data CI stops installing them | Low | Yes |
| 4 (optional) | Generate `uv.lock`, switch installs to `uv sync --frozen`, retire `requirements.txt` | Med | Yes |
| 5 (optional) | Relocate `rag_service/` -> `services/rag-service/`, add `packages/shared/`; update Docker context, `cloudbuild.yaml`, deploy workflow, Makefile | Med | Yes |

Validate after each phase: open a draft PR, confirm `gate` passes and that the right jobs run/skip via the Actions run graph, then merge.

## Expected outcome
- ~6 near-duplicate setups -> **1 composite action**; 3 duplicated data workflows -> **1 reusable workflow** + thin callers.
- Data/scheduled workflows stop installing `torch` -> minutes and cost drop substantially as the assistant lands.
- PRs only run the jobs they affect, gated by a single, reliable required check.
- One reproducible `uv.lock` for the whole repo; the RAG service's heavy deps stay isolated to its own image.

## Resume framing
- "Re-architected a Python monorepo's CI/CD on GitHub Actions: reusable workflows + composite actions to eliminate YAML duplication, PEP 735 dependency groups to keep multi-GB ML deps out of data pipelines, path-aware change detection with a gatekeeper required check, `uv` for hermetic 10-100x-faster installs, and OIDC/Workload Identity Federation for keyless Cloud Run deploys."

## Open decisions you can still flip
- New repo (migrate-with-history) vs the in-place restructure assumed here.
- Monorepo (assumed) vs splitting `rag-service` into its own repo.
- Full `uv` adoption (assumed, phases 4-5) vs keeping pip with layered requirement files.
