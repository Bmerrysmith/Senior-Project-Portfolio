# Handoff: Data Refinement Pipeline

This document is for teammates and future contributors who need to continue or
maintain the work added in the data refinement pipeline. It covers what's
running, why it's structured the way it is, how to operate it, and the
roadmap of what's intentionally left for the next person.

If you only read one section, read **"Mental model"** and **"Daily commands"**.

---

## Status (last updated 2026-06-19)

The pipeline is **up to date and fully wired**. Everything described below
is live on `main` and operational:

- **Minutes collection**: scrapes canonical PDF URLs from estero-fl.gov
  (Village Council + PZDB) into `app/data/minutes_index.json`. ✅
- **Bronze → silver refinement**: validation, cleaning, FK checks, atomic
  writes, run manifest, rejects file; now also confirms/replaces document
  URLs and sets `link_status` from the minutes index. ✅
- **Silver → gold (multi-deliverable)**: `build_gold()` emits several gold
  artifacts; the **GitHub Pages site loads ArcGIS gold**
  (`app/data/gold/arcgis_agenda_map_data.csv`) via `site_manifest.json`
  (`primary: arcgis`). Legacy meeting-level `meetings_public.csv` remains
  for silver-derived summaries. ✅
- **ArcGIS gold**: merged council + PZDB agenda items with item-level
  geocoded locations and `LandUseCategory`. ✅
- **Silver → Supabase publish**: idempotent, non-destructive, FK-safe,
  field-sliced upsert. Resilient to per-table failures and to secondary
  `UNIQUE(name)` collisions on reference tables (see "Recovering from
  drift" below). ✅
- **Supabase verify (redundancy check)**: read-back, diff vs silver,
  per-table drift report. ✅
- **98 tests passing** (cleaner, validator, minutes collector, meetings
  extractor, structured meeting-actions parsing, geocode stage, gold
  builder, API/router smoke tests, end-to-end, fake Supabase including
  unique-constraint + reset-reference paths, cleanup SQL generator,
  derived-meeting synthesis). ✅
- **Automation**: GitHub Actions CI on every push/PR, scheduled publish
  to Supabase nightly + on push to `main`, weekly data refresh
  (rescrape + rebuild silver/gold + commit + publish), monthly meetings
  discovery PR proposals, drift-watch every 6 hours, manual dispatch,
  local pre-commit hooks, Dependabot. ✅

What's **not** done is in the "Open issues" section near the bottom — those
are intentionally deferred for follow-up work, not bugs.

> If you re-run `python -m app.pipeline.run` right now you should see
> `meetings: in=100 out=176` (100 bronze Village Council + 76 synthesized
> PZ&DB), `arcgis ... rows: 321`, and `gold ... rows: 176` for the legacy
> meeting CSV. The committed gold artifacts should match
> (`git diff --exit-code app/data/silver/ app/data/gold/`), modulo
> minutes-index churn when estero-fl.gov posts new PDFs.

---

## Mental model

The repo follows a **medallion architecture**. Note the two serving copies:
a **gold layer** (multiple CSVs — see below) for the public GitHub Pages
site, and **Supabase** for ArcGIS API exports.

```
bronze (raw)        →   silver (validated, cleaned)   →   gold (public deliverables)
app/data/*.csv          app/data/silver/*.csv             app/data/gold/
                                                          arcgis_agenda_map_data.csv  ← website (primary)
                                                          meetings_public.csv         ← legacy meeting summary
                                                          meetings_ai_public.*        ← ML / RAG
                                                          meeting_actions_public.csv

normalized scripts  →   (source for ArcGIS gold)
normalized_csv_council/arcgis_agenda_map_data.csv
normalized_csv_pilot/.../arcgis_agenda_map_data.csv

                                                      →   Supabase Postgres         →  ArcGIS (export + feature_service)
                                                          projects, meeting_types,
                                                          locations, meetings, documents

reference (curated YAML, used by all stages)             minutes index (canonical PDF URLs)
app/data/reference/*.yaml                                 app/data/minutes_index.json
```

### Gold deliverables (read `app/data/gold/README.md`)

| File | Grain | Used by |
|------|-------|---------|
| **`arcgis_agenda_map_data.csv`** | Agenda item + geocoded site | **GitHub Pages** (`app.js`), map, ArcGIS |
| `meetings_public.csv` / `.json` | Meeting | Legacy summary; locations cleaned from ArcGIS |
| `meetings_ai_public.csv` / `.jsonl` | Agenda item + ML metadata | RAG / training |
| `meeting_actions_public.csv` | Action clause | Additive structured actions |
| `site_manifest.json` | Index | Frontend cache keys; `"primary": "arcgis"` |

`build_gold()` (`app/pipeline/publish/gold.py`) orchestrates:

1. **`build_arcgis_gold()`** — merge council + PZDB normalized ArcGIS CSVs,
   add `LandUseCategory`, write `arcgis_agenda_map_data.csv`.
2. **Legacy meeting CSV** — silver + reference + documents → `meetings_public.csv`,
   then **`clean_meetings_public_rows()`** overlays ArcGIS locations where matched.
3. **`build_ai_gold()`** — enriched agenda-item CSV/JSONL from ArcGIS gold.
4. **`site_manifest.json`** — registry with hashes; frontend loads ArcGIS via
   `manifest.arcgis.csv`.

The public site (`index.html` / `app.js`) loads **`manifest.arcgis`** (not
`meetings_public`). Supabase remains the serving copy for ArcGIS API routers.

Three rules to keep in your head:

1. **Bronze is sacred.** Never edit `app/data/silver/` by hand — it's regenerated
   from bronze by the pipeline. If silver is wrong, fix bronze (the CSV) or fix
   the pipeline (`app/pipeline/`).
2. **Silver is the canonical source of truth.** Supabase is the *serving copy*.
   Anything in Supabase that differs from silver is "drift," and the verify
   stage will surface it.
3. **The pipeline never deletes from Supabase.** It only upserts. If you need
   to remove rows, do it explicitly in the Supabase dashboard.

---

## Repository map (pipeline-relevant pieces only)

```
app/
├── data/
│   ├── meetings.csv               BRONZE  raw meeting rows (edit to add records)
│   ├── documents.csv              BRONZE  raw document rows
│   ├── reference/                 REFERENCE  human-curated lookups (edit freely)
│   │   ├── projects.yaml
│   │   ├── meeting_types.yaml
│   │   ├── locations.yaml         (lat/long lives here)
│   │   └── geometries.yaml        (LineString / Polygon coords by location_id)
│   ├── silver/                    GENERATED  do not hand-edit
│   │   ├── meetings.csv
│   │   ├── documents.csv          (real documents only)
│   │   ├── documents_planned.csv  (future placeholders, isolated)
│   │   ├── meeting_actions.csv    parsed clauses from action_taken blobs
│   │   └── _rejects.json          (rows that failed validation, with reasons)
│   ├── gold/                      GENERATED  do not hand-edit (see gold/README.md)
│   │   ├── site_manifest.json     index; primary=arcgis for the website
│   │   ├── arcgis_agenda_map_data.csv  PRIMARY public dataset (agenda items)
│   │   ├── meetings_public.csv    legacy meeting-level summary
│   │   ├── meetings_ai_public.csv / .jsonl  ML / RAG deliverables
│   │   └── meeting_actions_public.csv  additive structured actions feed
│   ├── minutes_index.json         GENERATED  canonical PDF URLs scraped from estero-fl.gov
│   ├── extract/
│   │   └── candidate_meetings.csv GENERATED  newly discovered meetings for PR review
│   ├── runs/                      GENERATED & gitignored  per-run manifest
│   │   └── <UTC-timestamp>/manifest.json
│   ├── csv_store.py               read-only store over silver/bronze (backs the JSON/GeoJSON API)
│   └── mock.py                    in-memory seed store (unused, intentionally kept; get_store() returns CSVStore)
│
├── pipeline/                      THE PIPELINE
│   ├── config.py                  filesystem paths (bronze/silver/gold/minutes), Estero bbox
│   ├── reference.py               YAML loader (cached, has reload())
│   ├── clean/text.py              OCR-artifact cleaner; pure functions, well-tested
│   ├── clean/actions.py           structured action parser (kind/ref/amount heuristics)
│   ├── collect/minutes.py         scrape estero-fl.gov → minutes_index.json (+ pure parsers)
│   ├── extract/meetings.py        discover newly-held meetings → candidate_meetings.csv
│   ├── enrich/geocode.py          optional US Census geocoder with JSON cache
│   ├── validate/schemas.py        Pydantic models + FK checks + reject collection
│   ├── load/silver.py             bronze → silver (atomic writes, dup checks, minutes enrich)
│   ├── publish/gold.py            orchestrates gold build + site manifest
│   ├── publish/arcgis_gold.py     normalized ArcGIS → gold arcgis_agenda_map_data.csv
│   ├── publish/arcgis_clean.py    overlay ArcGIS locations onto meetings_public
│   ├── publish/ai_gold.py         ArcGIS gold → ML/RAG CSV + JSONL
│   ├── publish/supabase.py        silver+reference → Supabase (idempotent upsert)
│   ├── verify/supabase.py         Supabase → diff vs silver+reference (drift report)
│   ├── recover/cleanup_sql.py     emits "delete remote extras" SQL (operator tool)
│   └── run.py                     CLI orchestrator + run-manifest writer
│
├── routers/                       FastAPI read-API
│   ├── export.py                  LIVE  Supabase-backed CSV exports for ArcGIS
│   ├── feature_service.py         LIVE  Esri Feature Service endpoint
│   ├── {meetings,projects,documents,meeting_types,locations,layers}.py
│   │                               MOUNTED silver-backed JSON/GeoJSON read-API under /api/v1 (see issue #5)
│   └── actions.py                 structured meeting-actions API (created, not mounted)
│
├── services/geojson.py           GeoJSON builders for the layers router
├── dependencies.py               get_store() — single swap point for the data layer
├── db.py                          Supabase client (get_client, try_get_client)
├── main.py                        FastAPI app: mounts all routers + serves /dashboard
├── static/dashboard.html         elderly-accessible interactive Leaflet map (served at /dashboard)
├── ../dashboard.html             GitHub Pages-compatible static dashboard entrypoint
└── ...

scripts/
├── scrape_minutes_index.py        CLI shim → app.pipeline.collect.minutes.collect_minutes_index()
└── scrape_meetings.py             CLI shim → app.pipeline.extract.meetings.collect_candidate_meetings()

tests/                             pytest, no external dependencies
├── test_clean_text.py             OCR-artifact cleaning cases
├── test_validate.py               Pydantic schema + FK validation cases
├── test_silver_synthesis.py       derived-meeting synthesis from documents
├── test_minutes_collector.py      minutes filename/date parsing + URL resolution
├── test_gold.py                   gold schema + join behaviour
├── test_meeting_actions.py        structured action parsing + silver output
├── test_extract_meetings.py       meetings discovery parsing + bronze diffing
├── test_geocode.py                geocoder cache/no-op behavior
├── test_api_routers.py            mounted /api/v1 router smoke tests
├── test_pipeline_e2e.py           runs the pipeline against real bronze
├── test_recover_cleanup_sql.py    cleanup-SQL generator
└── test_supabase_publish_verify.py  uses an in-process FakeSupabaseClient
```

---

## Daily commands

The `Makefile` is the primary command surface. Run `make help` for the full menu.

```bash
make install-dev          # one-time setup: venv, deps, pre-commit hooks
make build                # build silver + gold locally, no network
make test                 # run pytest
make publish              # publish silver to Supabase + verify (needs SUPABASE_*)
make publish-dry          # preview publish without remote calls
make verify               # read-only Supabase diff
make ci                   # strict pipeline + tests (what CI runs)
make run-server           # uvicorn on :8000
```

If you prefer the raw commands:

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Refresh canonical PDF URLs from estero-fl.gov (network; updates minutes_index.json)
python scripts/scrape_minutes_index.py

# Build silver + gold / test / publish
python -m app.pipeline.run                                              # offline (silver + gold)
python -m app.pipeline.run --strict                                     # fail on rejects
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run --publish --verify
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run --publish --dry-run

pytest -q                                                               # tests
uvicorn app.main:app --reload                                           # FastAPI dev server
```

### Strict-mode exit codes

`--strict` is what CI uses; it makes the pipeline turn warning-level
findings into a non-zero exit so the workflow fails loudly. The codes are
distinct so you can tell at a glance what kind of failure happened:

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `2`  | Silver build had rejected rows (validation failures) |
| `3`  | Verify reported drift between silver+reference and Supabase |
| `4`  | Publish recorded a per-table error (e.g. PostgREST `23505` on a unique constraint) |

The code is the *highest* one that applied — so a run with both rejects
and drift reports `2`, but a run with only drift reports `3`.

## Automation

Pipeline runs in six different ways without anyone clicking a button:

| Trigger | What runs | Where |
|---|---|---|
| Every push & PR | `pytest -q`, `python -m app.pipeline.run --strict`, "silver matches commit" guard | `.github/workflows/ci.yml` |
| Push to `main` (data/pipeline files) | `python -m app.pipeline.run --publish --verify --strict` | `.github/workflows/publish.yml` |
| Nightly at 06:00 UTC | Same publish + verify pass — re-asserts canonical state | `.github/workflows/publish.yml` (schedule) |
| Weekly Mon 07:00 UTC | Rescrape minutes → rebuild silver+gold → commit refreshed artifacts to `main` → publish + verify (strict) | `.github/workflows/refresh-data.yml` |
| Monthly | Discover newly-held meetings from estero-fl.gov and open a PR with `app/data/extract/candidate_meetings.csv` (human merge gate) | `.github/workflows/discover-meetings.yml` |
| Every 6 hours | `python -m app.pipeline.run --verify --strict` (read-only drift watch) | `.github/workflows/drift-watch.yml` |
| Operator-triggered | Manual `workflow_dispatch` from the Actions UI (publish or refresh) | `.github/workflows/publish.yml`, `.github/workflows/refresh-data.yml` |
| Local `git commit` (after `make install-dev`) | Pre-commit framework: rebuilds silver if you touched bronze/reference, stages the regenerated outputs into your commit | `.pre-commit-config.yaml` |

The **weekly refresh** is what keeps the public site current: it commits
the regenerated gold CSV back to `main`, so GitHub Pages serves fresh data
without anyone running the pipeline by hand. It commits with `[skip ci]` to
avoid a redundant publish from the push trigger.

**One-time setup for the GitHub workflows:** in *Settings → Secrets and variables → Actions* on the GitHub repo, add `SUPABASE_URL` and `SUPABASE_KEY` (or `SUPABASE_SERVICE_KEY`). The workflows skip cleanly when secrets aren't set, so a fork or anyone without access can still run CI.

If you want the API health check to run in CI, also set the repo variable `RUN_API_HEALTH=true` in *Settings → Secrets and variables → Actions → Variables*.

**Dependabot** (`.github/dependabot.yml`) watches Python deps and GitHub Actions weekly; you'll see grouped PRs ("patches" / "minors") to review.

---

## Recovering from drift

Two failure modes show up regularly and are worth understanding:

### A) Per-table publish error (e.g. `PostgREST 23505`)

Symptom in the workflow log:

```
duplicate key value violates unique constraint "meeting_types_type_name_key"
Key (type_name)=(...) already exists.
```

What happens now:

1. The publish step **does not abort** anymore. The offending table's
   report records `"error": "..."` and the rest of `publish` (other
   tables) plus `verify` still run.
2. For reference tables (`projects`, `meeting_types`, `locations`) the
   publish also pre-flights against remote rows that already use a
   row's stable name (`project_name` / `type_name` / `location_name`)
   with a different primary key. Those rows are **skipped** and recorded
   under `"name_conflicts"` / `"name_conflict_count"` in the per-table
   report, so `--strict` flags them via the new exit code `4`.

The next person looks at the manifest's `stages.publish.<table>` and
sees exactly which rows couldn't land and why.

### B) Remote IDs disagree with the YAML (`--reset-reference`)

Sometimes the Supabase project was seeded by an earlier import with a
different `type_id ↔ type_name` mapping (or a different `project_id`,
`location_id` mapping) than the canonical YAML. Plain upserts can't
fix this, because they can't change a row's primary key without breaking
foreign keys, and we never delete remote data implicitly.

For this case there is now an **explicit, opt-in** escape hatch:

```bash
# Always preview first.
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run \
  --reset-reference --publish --verify --dry-run

# When you're confident, run for real.
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run \
  --reset-reference --publish --verify --strict
```

`--reset-reference` deletes every row from `projects`, `meeting_types`,
and `locations` on the remote, then `--publish` reseeds them from YAML
with the correct IDs. **It does not touch `meetings` or `documents`.**
Those are larger, FK-bearing, and may contain user-curated state, so
they're cleaned up out of band in the Supabase dashboard if at all.

Operator checklist when you reach for `--reset-reference`:

1. Confirm there are no human edits to `projects` / `meeting_types` /
   `locations` on the remote you'd lose. (These tables are
   YAML-canonical, so this should be a non-event.)
2. Run with `--dry-run` first; the manifest's `stages.reset_reference`
   block tells you `would_delete` per table.
3. Run for real. The `delete` happens before the `publish`, so a single
   command takes the remote from "drifted" to "matches YAML."
4. `--verify --strict` at the end of the same command confirms
   everything is `in_sync`. CI's drift-watch will pass on the next tick.

### What `--reset-reference` will **not** fix

The 133 extra `meetings` and 169 extra `documents` rows shown by
drift-watch are remote rows the pipeline never published. Those need to
be triaged manually — but you don't have to copy IDs by hand. A
generator at `app/pipeline/recover/cleanup_sql.py` reads the current
silver CSVs and reference YAML and emits a paste-into-Supabase SQL
script keyed on `NOT IN (<canonical ids>)`:

```bash
python -m app.pipeline.recover.cleanup_sql > cleanup.sql
# Inspect cleanup.sql, then paste it into the Supabase SQL editor.
```

The generated script is wrapped in `BEGIN … ROLLBACK`, so the first run
just prints a row count per table without changing anything; promote
the trailing `ROLLBACK` to `COMMIT` once you're satisfied. Delete order
is documents → meetings → locations → meeting_types → projects so no
statement orphans a child row.

Your options for the extras are unchanged:

- **Delete them** (most common): run the generated script. One pass and
  drift-watch goes green.
- **Promote them** into the canonical CSV/YAML by adding the rows to
  bronze and rerunning the pipeline.
- **Keep them** (and accept that drift-watch will keep flagging them).

This was an intentional design choice: the pipeline never deletes
operational data on its own. See "Architectural decisions worth not
undoing."

---

## How to add new data

### Add a new project

1. Edit `app/data/reference/projects.yaml`. Add an entry with the next
   available `project_id`.
2. Run `python -m app.pipeline.run --publish --verify`.
3. The new project is now in Supabase and ArcGIS can see it.

### Add a new location (with lat/long)

1. Edit `app/data/reference/locations.yaml`. Make sure `latitude` /
   `longitude` are inside the Estero bounding box (≈ 26.30–26.55 N,
   −81.95 to −81.65 W).
2. If it's a road or trail, also add a coordinate sequence under
   `road_geometries:` in `geometries.yaml` keyed by the same `location_id`.
3. Run the pipeline.

### Add new meeting records

1. Append rows to `app/data/meetings.csv` (this is the bronze layer).
2. Make sure the `project_id` and `type_id` exist in the reference YAML —
   the pipeline's FK checks will reject the row otherwise and you'll see
   the row in `app/data/silver/_rejects.json`.
3. Run the pipeline.

### Add new documents

Same as meetings, but in `documents.csv`. If a new document references a
`meeting_id` that doesn't exist in `meetings.csv`, the pipeline will
automatically synthesize a PZ&DB meeting for it (assuming
`type_name = "Planning Zoning & Design Board"`). If the document is for
a different governing body, add a new entry to
`SYNTHESIZED_MEETING_DEFAULTS` in `app/pipeline/load/silver.py` mapping
the `type_name` to the right `(type_id, project_id, location_id)`.

---

## How to read a run

After every `python -m app.pipeline.run` you get a manifest at
`app/data/runs/<timestamp>/manifest.json`. Open it; every section is
human-readable. The fields you care about most:

- `stages.silver.meetings.{in, out, rejects}` — did anything fail validation?
- `stages.silver.meetings.out_bronze` / `out_synthesized` — split of bronze Village Council rows vs. PZ&DB rows derived from documents
- `stages.silver.documents.fk_warnings` — count of docs with broken FK to meetings (should be 0 after the synthesis step; if it's not, something has regressed)
- `stages.publish.<table>.upserted` — how many rows we wrote to Supabase per table
- `stages.publish.<table>.error` — present iff that table's upsert raised; the message is captured here and the rest of `publish` still ran
- `stages.publish.<table>.name_conflicts` — local rows that share a `name_field` with a different-PK remote row and were skipped (reference tables only); see "Recovering from drift"
- `stages.reset_reference.<table>.deleted` — present iff `--reset-reference` ran; how many rows we deleted (or `would_delete` under `--dry-run`)
- `stages.verify.<table>.in_sync` — `true` if Supabase agrees with silver for this table
- `stages.verify.<table>.in_local_only_sample` / `in_remote_only_sample` — first 50 PKs that disagree
- `stages.verify.<table>.mismatched_sample` — first 10 rows where field values differ, with `local` and `remote` values

If you see a non-empty `_rejects.json` after a run, the file has a
`row` (the original CSV row) and `errors` (human-readable list of what was
wrong). Fix the source CSV/YAML, re-run.

---

## Open issues — work the next person should pick up

These are real problems the pipeline surfaced or that were intentionally
left in scope for a follow-up.

### 1. Document → Meeting FK mismatch (RESOLVED 2026-05-11)

**History.** `documents.csv` is PZ&DB minutes (`type_id=2`, dates
2021–2026) and `meetings.csv` is Village Council meetings (`type_id=1`,
dates 2015–2026). They have **zero overlap** in `meeting_id`, date, *or*
type — they're feeds for two different governing bodies. For a long
time the pipeline carried this as 76 `fk_warnings` and the publish to
Supabase relied on the remote `documents_meeting_id_fkey` constraint
being unenforced. Once the legacy "extras" were cleaned out of Supabase,
the FK started rejecting inserts (`23503`) and documents couldn't
publish.

**Fix.** `load/silver.py` now synthesizes a PZ&DB meeting row per
unique `meeting_id` in `documents.csv` (see "Derived meetings" in that
module's docstring). Defaults are deterministic and live in
`SYNTHESIZED_MEETING_DEFAULTS`:

| type_name in document | type_id | project_id | location_id |
|---|---|---|---|
| Planning Zoning & Design Board | 2 | 4 (PZ&DB General Meeting Records) | 6 (Council Chambers) |

The silver `meetings.csv` now contains 100 bronze Village Council rows
plus 76 synthesized PZ&DB rows (total 176), and `fk_warnings` is `0`.
Synthesized rows are clearly marked with `notes = "Derived from
document feed (no bronze meetings row)."` so they're easy to filter or
audit downstream. The run manifest carries `stages.silver.meetings.{
out_bronze, out_synthesized }` for visibility.

**Adding a new document feed.** If a future scraper introduces minutes
for another governing body (e.g. School Board), add an entry to
`SYNTHESIZED_MEETING_DEFAULTS` mapping the `type_name` to the right
`(type_id, project_id, location_id)`. Documents with an unrecognised
`type_name` go to the rejects file with an actionable error.

### 2. Structured `meeting_actions` (DONE 2026-05-28)

The `action_taken` blob is now exploded during silver build into:

```
meeting_actions
  action_id (PK)
  meeting_id (FK)
  sequence  (0, 1, 2, ...)
  kind      ("Adopted Resolution" | "Approved Contract" | ...)
  reference_code  ("2024-07")
  amount_usd  (NUMERIC, nullable)
  raw_text  (the cleaned clause)
```

Backed files/modules:

- `app/data/silver/meeting_actions.csv`
- `app/data/gold/meeting_actions_public.csv` (additive; existing 14-col meetings gold unchanged)
- parser helpers in `app/pipeline/clean/actions.py` (`kind`, `reference_code`, `amount_usd`, `raw_text`)
- API surface in `app/routers/actions.py` (**created but not mounted**)

This unlocks SQL/API filtering like "show approved contracts over $100k."

### 3. Meetings scraper/discovery (PARTIALLY ADDRESSED 2026-05-28)

A minutes collector now lives at `app/pipeline/collect/minutes.py` (CLI
shim at `scripts/scrape_minutes_index.py`). It scrapes canonical PDF URLs
from estero-fl.gov's Village Council + PZDB minutes index pages into
`app/data/minutes_index.json`, and the silver build uses that index to
confirm/replace document URLs and set `link_status`. The weekly
`refresh-data.yml` workflow keeps it current.

This now exists as a proposal stage:

- `app/pipeline/extract/meetings.py`
- `scripts/scrape_meetings.py`
- `.github/workflows/discover-meetings.yml` (monthly + manual)
- output: `app/data/extract/candidate_meetings.csv`

It discovers newly-held meetings and opens a PR with candidate rows for
human review. It still **does not auto-edit bronze**, by design.

### 4. Geocoding stage (PARTIALLY DONE 2026-05-28)

`app/pipeline/enrich/geocode.py` now exists with a cache path
(`app/data/reference/geocode_cache.json`) and offline-testable behavior.
It is intentionally optional and currently a no-op for today's reference
set (all locations already have coordinates).

Related geo coverage improvement already landed: `geometries.yaml` now has
real area polygons for the three septic zones (`location_id` 2/3/4), so
`/api/v1/layers/areas` no longer relies only on fallback centroid boxes.

### 5. The CSV/silver-backed read-API — MOUNTED ✅

`app/routers/{projects,meetings,meeting_types,locations,layers,documents}.py`
are a typed JSON + GeoJSON read-API (initial commit `5292f92`, authored by
Ethan Malavia). They use `app/dependencies.py::get_store()` →
`app/data/csv_store.py` (and `app/services/geojson.py` for the `layers`
router), which serves the **canonical silver layer** (falling back to
bronze).

**Status: done.** All six routers are now mounted in `app/main.py` under
`settings.api_v1_prefix` (`/api/v1`), alongside the unchanged
Supabase-backed `export` and `feature_service`. Because the store reads
silver, these endpoints are *not* a competing source of truth; they expose
the same canonical data the pipeline produces, as filterable JSON
(`/api/v1/meetings?project_id=…`) and ArcGIS-ready GeoJSON
(`/api/v1/layers/points`). The whole read-API works with **no Supabase
credentials**.

On top of the read-API, an **elderly-accessible interactive map dashboard**
is served at **`/dashboard`** (`app/static/dashboard.html`, Leaflet +
OpenStreetMap, vanilla JS, same-origin so no CORS). See the README
"Interactive dashboard" subsection.

For static GitHub Pages hosting, `dashboard.html` at the repo root provides
the same experience without FastAPI routing by reading generated CSV/YAML
files directly.

Cleanups completed at the same time:

- The router `store:` annotations were switched from `MockStore` to
  `CSVStore` (matching what `get_store()` actually returns).
- `app/data/mock.py` is **intentionally kept but unused** (it is not
  imported anywhere now). It remains as reference seed data; delete it only
  if a future cleanup wants to remove the dead code.
- `tests/test_api_routers.py` is a credential-free `TestClient` smoke test
  that builds an app from just these routers (so it doesn't import
  `app.main` / the `supabase` path) and asserts each endpoint returns 200
  against the committed silver.

Possible follow-ups: tighten CORS for production, and populate
`area_geometries` in `geometries.yaml` so `/api/v1/layers/areas` returns
real polygons (currently it falls back to small centroid boxes for
Infrastructure/Park/Development locations that have coordinates).

### 6. CI is configured but secrets need to be set

`SUPABASE_URL` / `SUPABASE_KEY` need to be added in the GitHub repo's
*Settings → Secrets and variables → Actions* before `publish.yml` and
`drift-watch.yml` can do anything useful. Without them the workflows
still pass (the pipeline gracefully skips publish/verify), but they
won't actually publish to Supabase or detect drift.

---

## Architectural decisions worth not undoing

These are the design choices that make the pipeline professional rather
than ad-hoc — please push back on PRs that try to undo them.

1. **Reference data lives in YAML, not Python.** Non-developers can edit
   it. Don't move it back into `csv_store.py`.
2. **Pipeline never deletes from Supabase.** Drift gets reported; resolving
   it is an operator's call. Don't add an "auto-cleanup" mode that
   silently destroys remote rows.
3. **Atomic writes in `load/silver.py`.** The pipeline writes to a
   tempfile, then `os.replace`s it. A crashed run never corrupts silver.
   Don't replace this with a plain `open(..., "w")`.
4. **Validation rejects are non-fatal by default.** Bad rows go to
   `_rejects.json`, the pipeline keeps going on the good rows. Use
   `--strict` if you need CI to fail on them.
5. **`from __future__ import annotations` everywhere in `app/pipeline/`.**
   Annotations are strings, not runtime types. This lets the pipeline run
   on Python 3.9 even though the FastAPI service requires 3.10+.
6. **Tests don't require Supabase credentials.** `test_supabase_publish_verify.py`
   uses an in-process `FakeSupabaseClient` stub. Keep it that way; if a
   teammate adds tests that hit real Supabase, they'll break in CI.

---

## Useful pointers

- **Pydantic schemas** for the *pipeline* (strict, with FK checks) live in
  `app/pipeline/validate/schemas.py`. The Pydantic schemas for the *API*
  (the contract with ArcGIS) live in `app/models/schemas.py`. They look
  similar but serve different purposes — don't merge them.
- **The `action_taken` cleaner** is a list of regex `(pattern, replacement)`
  pairs. To handle a new OCR artifact, add a pair in
  `app/pipeline/clean/text.py::_SPLIT_VERB_FIXES` and a unit test in
  `tests/test_clean_text.py`. The cleaner is pure (no I/O), so testing is
  trivial.
- **Adding a new pipeline stage** (e.g. geocoding) follows the same pattern
  as `publish/supabase.py`: a module under `app/pipeline/<stage>/`, a
  function that takes a client/config and returns a report dict, plus a
  flag in `run.py` and a manifest section. Keep stages pure if possible.
- **GitHub Pages** (`index.html` / `app.js`) loads **ArcGIS gold** from
  `site_manifest.json` → `manifest.arcgis.csv`
  (`app/data/gold/arcgis_agenda_map_data.csv`). Each row is one agenda item
  with geocoded address, lat/lon, land-use category, and PDF link. Full-text
  search uses MiniSearch over that dataset. Fallback URL:
  `ARCGIS_CSV_URL` in `app.js`. The legacy `meetings_public.csv` is still
  generated for meeting-level summaries but is **not** what the site loads.
  Regenerate gold with `python -m app.pipeline.run`; the weekly
  `refresh-data.yml` workflow commits all gold artifacts to `main`.
- **The `Estero bounding box`** is `app/pipeline/config.py::ESTERO_BBOX`.
  Use it in any new geo-validation code so the bounds stay consistent.

---

## Contacts

| Role | Person |
|---|---|
| Original implementation (refinement pipeline) | Nolan Stilwell-Carroll |
| Supabase / database architecture | Krish Shah |
| Queries / docs | Ethan Malviala |
| Community partner | Terry Flanagan (Engage Estero / EsteroToday.com) |
| ArcGIS / StoryMap | Kim Dailey |
| Faculty | Dr. Vinod Ahuja, COP 3710, FGCU |

If you're stuck on the pipeline specifically, the run manifest plus the
`_rejects.json` will tell you 90% of what you need. The next 10% is
either in the docstrings of `app/pipeline/*.py` or in the test files,
which double as worked examples.
