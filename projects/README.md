# Project Source

Curated source from two of my projects. These are excerpts, not full mirrors.
Data files, vector indexes, and scraped PDFs are left out to keep the repo light.

For full history and the complete trees, see the original repos:

- **EagleGIS** — https://github.com/EagleGIS-FGCU/EagleGIS
- **ORION** — https://github.com/krocks9903/-GenAi-fund-advisor-Summer-Internship-2025

## eaglegis/

Civic transparency platform for the Village of Estero. What's here:

- `app/pipeline/` — the bronze to silver to gold data pipeline (collect, clean, validate, enrich, publish, verify)
- `app/routers/`, `app/models/`, `app/services/` — FastAPI read-API serving JSON and GeoJSON
- `app/data/reference/` — YAML reference data (projects, meeting types, locations, geometries)
- `app/data/sample/` — 25-row samples of the gold CSV output so you can see the schema
- `rag_service/` — RAG service and its container setup
- `scripts/` — scrapers and CSV builders
- `tests/` — pytest suite, no credentials needed
- `.github/workflows/` — CI, weekly refresh, monthly meeting discovery, drift watch
- `index.html`, `dashboard.html` — public site and accessible Leaflet map
- `HANDOFF.md` — maintainer guide

Left out: scraped meeting PDFs (`data/raw/`), the normalized CSV exports, and the
full gold and silver data files. All regenerable by running the pipeline.

## orion/

AI mutual fund advisor built during my Infosys internship. What's here:

- `Scripts/` — Streamlit app, RAG index build, PDF processing, risk metric calcs (Sortino, max drawdown)
- `Data/` — fund metadata, risk metrics, definitions, a sample prospectus
- `App_Data/jobs/` — scheduled scraper job
- `Dockerfile`, `.github/workflows/` — container build and Azure deploy

Left out: the FAISS vector index (14MB, rebuildable from `Scripts/Index.py`) and
the app log. The Azure deployment is no longer live.
