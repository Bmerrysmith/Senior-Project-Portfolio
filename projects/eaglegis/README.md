# Village of Estero Public Meetings and Legislation Database

A PostgreSQL-based relational database system for cataloging, organizing, and spatially mapping Village of Estero public meeting records. Built in partnership with Engage Estero (EsteroToday.com) to support municipal transparency and civic engagement through geospatial integration with ArcGIS StoryMaps.

Developed as part of COP 3710 - Database Systems at Florida Gulf Coast University under Dr. Vinod Ahuja.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Team](#team)
3. [Community Partner](#community-partner)
4. [Repository Structure](#repository-structure)
5. [Database Schema](#database-schema)
6. [Getting Started](#getting-started)
7. [Web Scraper](#web-scraper)
8. [Populating the Database](#populating-the-database)
9. [Running Queries](#running-queries)
10. [ArcGIS Export](#arcgis-export)
11. [Maintenance Guide for Future Teams](#maintenance-guide-for-future-teams)
12. [Technologies Used](#technologies-used)
13. [License](#license)

---

## Project Overview

The Village of Estero, incorporated in 2014, holds regular public meetings where council members discuss zoning decisions, infrastructure projects, and community policy. These meeting records are scattered across PDFs, spreadsheets, and web pages with no centralized or searchable system.

This project addresses that gap by providing:

- A BCNF-normalized relational database hosted on Supabase (cloud PostgreSQL) that stores meeting records, associated documents, project metadata, meeting type classifications, and geographic locations.
- A Python web scraper that extracts meeting data from the Village of Estero website (estero-fl.gov).
- SQL queries for searching, filtering, and analyzing meeting history across projects.
- CSV export functionality with latitude and longitude coordinates for direct import into ArcGIS StoryMaps, enabling Estero residents to visually explore active projects, meeting locations, and council decisions on an interactive map.

### Data Pipeline

The data flows through the following stages:

1. **Source**: Village of Estero public meeting pages (estero-fl.gov)
2. **Collection**: Python web scraper extracts meeting records, dates, and document links
3. **Cleaning**: Raw data is structured, validated, and normalized
4. **Storage**: Data is loaded into five BCNF-normalized tables on Supabase PostgreSQL
5. **Output**: SQL queries for analysis and CSV exports with geospatial coordinates for ArcGIS

#### Refinement pipeline (bronze → silver → gold)

Raw CSVs in `app/data/` are treated as the **bronze** layer. A small Python
pipeline validates and cleans them into a **silver** layer, then denormalizes
silver into a **gold** public CSV that the GitHub Pages site serves. Supabase
is a parallel serving copy for ArcGIS.

```
bronze:    app/data/meetings.csv, app/data/documents.csv
reference: app/data/reference/*.yaml  (projects, meeting_types, locations, geometries)
minutes:   app/data/minutes_index.json  (canonical PDF URLs scraped from estero-fl.gov)
silver:    app/data/silver/meetings.csv, documents.csv, documents_planned.csv, meeting_actions.csv, _rejects.json
gold:      app/data/gold/meetings_public.csv, meeting_actions_public.csv
extract:   app/data/extract/candidate_meetings.csv  (newly discovered meetings for PR review)
runs:      app/data/runs/<UTC-timestamp>/manifest.json
```

Run it with:

```bash
python scripts/scrape_minutes_index.py           # refresh minutes_index.json (network)
python scripts/scrape_meetings.py                # discover newly-held meetings (proposal CSV only)
python -m app.pipeline.run                       # build silver + gold (offline)
python -m app.pipeline.run --publish             # silver + gold + upsert into Supabase
python -m app.pipeline.run --verify              # silver + gold + diff vs Supabase
python -m app.pipeline.run --publish --verify    # publish then redundancy check (recommended)
python -m app.pipeline.run --publish --dry-run   # print what would be sent, no calls
python -m app.pipeline.run --strict              # exit !=0 on any rejects (2) or drift (3)
```

What the pipeline does:

- Validates every row against Pydantic schemas (`app/pipeline/validate/schemas.py`)
  with FK checks against reference data (project_id, type_id, location_id).
- Cleans OCR artifacts in `action_taken` (e.g. "Approve d" → "Approved",
  "A ccept ed" → "Accepted", non-breaking hyphens, smart quotes — see
  `app/pipeline/clean/text.py`).
- Enriches documents against `minutes_index.json`: replaces guessed PDF URLs
  with confirmed canonical estero-fl.gov links and sets `link_status`
  (Uploaded / Missing) accordingly.
- Splits `documents_planned.csv` (future placeholder rows) out of the real
  `documents.csv` so analytics never mixes planned with published.
- Builds the **gold** public CSV (`app/pipeline/publish/gold.py`): joins
  silver meetings + reference + documents + minutes into the exact 14-column
  schema `index.html` parses (`ProjectName, MeetingType, MeetingDate,
  MeetingYear, Status, ActionTaken, StartTime, StaffCode, Title, MinutesURL,
  DocDate, LocationName, Latitude, Longitude`).
- Parses structured meeting actions from `action_taken` into
  `app/data/silver/meeting_actions.csv` and additive
  `app/data/gold/meeting_actions_public.csv`.
- Writes a run manifest with input/output row counts per stage, reject counts,
  output file SHA-256 hashes, and the git SHA — making each run reproducible.

#### Collecting canonical PDF links (minutes index)

`app/pipeline/collect/minutes.py` scrapes the Village Council and PZDB minutes
index pages on estero-fl.gov, parses dates out of the PDF filenames, and writes
`app/data/minutes_index.json` keyed by body (`council` / `pzdb`) and ISO date.
Run it directly via the CLI shim `scripts/scrape_minutes_index.py`. The silver
build and gold build both consume this index so the public site links straight
to the authoritative PDFs.

#### Discovering newly-held meetings (proposal stage)

`app/pipeline/extract/meetings.py` discovers newly-held meetings from
estero-fl.gov, diffs against the current bronze layer, and writes
candidate rows to `app/data/extract/candidate_meetings.csv` for **human
review** (never auto-edits bronze). Run via:

```bash
python scripts/scrape_meetings.py
```

Automation: `.github/workflows/discover-meetings.yml` runs monthly (and
on manual dispatch) and opens a PR when new candidates are found.

#### Geocode enrichment stage

`app/pipeline/enrich/geocode.py` provides an optional US Census Geocoder
stage with a JSON cache at `app/data/reference/geocode_cache.json`. It is
offline-testable and currently a no-op with the committed reference data
because all locations already have coordinates.

#### Publishing to Supabase (serving copy for ArcGIS)

Supabase is the ArcGIS-facing serving copy. The publish stage upserts silver +
reference data into the corresponding tables (`projects`, `meeting_types`,
`locations`, `meetings`, `documents`):

- **Idempotent**: repeated runs produce the same end state.
- **Non-destructive**: never deletes rows from Supabase; drift is reported.
- **FK-safe**: parents (projects, meeting_types, locations) are upserted
  before children (meetings, documents).
- **Field-sliced**: silver helpers like `documents.meeting_year` are
  dropped before write so only Supabase-schema columns are sent.
- Requires `SUPABASE_URL` and `SUPABASE_KEY` (or `SUPABASE_SERVICE_KEY`)
  in the environment. If unset, the stage logs a warning and skips.

#### Verifying against Supabase (redundancy check)

The verify stage reads each Supabase table back and diffs against
silver+reference. The drift report (per table) goes into the run manifest:

- `in_local_only` — silver has rows Supabase doesn't (need a publish)
- `in_remote_only` — Supabase has rows silver doesn't (manual edits / drift)
- `mismatched` — same primary key, different field values

Combine with `--strict` to fail CI on any drift.

Tests live under `tests/`; run with `pytest -q`. The Supabase tests use an
in-process fake client and do not require credentials.

#### GitHub Pages frontend (`index.html`)

The public-facing **EagleGIS Meeting Document Tracker** is a single-page site
committed at the repo root. When [GitHub Pages](https://pages.github.com/) is
enabled for this repository (typically deploying from branch `main` at `/`), it
loads the pipeline-generated **gold** CSV over HTTP — see `CSV_URL` in
`index.html`, which points to the relative path
[`app/data/gold/meetings_public.csv`](app/data/gold/meetings_public.csv) on
`main`. **Important:** Pages does not talk to Supabase or the FastAPI layer;
anything shown there is whatever is in that gold CSV. The gold CSV is produced
by `build_gold()` (`app/pipeline/publish/gold.py`) on every
`python -m app.pipeline.run`, and the weekly `refresh-data.yml` workflow
rescrapes minutes, rebuilds it, and commits it back to `main` — so the
citizen-facing site stays in sync automatically. If you rebuild locally,
commit the regenerated `app/data/gold/meetings_public.csv`.

**Search.** The sidebar search box builds a [**MiniSearch**](https://github.com/lucaong/minisearch)
index in memory after parse (CDN `minisearch@7.1.0`). Queries use token-level
matching with BM25 relevance, **prefix**, **light fuzziness** (~0.2), and boosted
weights on titles and long `ActionTaken` text. Multiple words combine with logical
AND. If the CDN script fails to load, filtering falls back to plain substring matching
over the major columns — same limitation as earlier releases.

Some records were also entered manually by the team where web data was incomplete or unavailable. Requirements and feedback from community partner Terry Flanagan guided the database design and query development throughout the project.

---

## Team

| Name | Role |
|------|------|
| Krish Shah | Requirements Gathering, Database Architect |
| Nolan Stillwell | ArcGIS Implemnetation & Data Population |
| Ethan Malviala | Query Development and Documentation |

---

## Community Partner

**Engage Estero / EsteroToday.com**
Partner Contact: Terry Flanagan

Engage Estero is a civic organization that monitors Village of Estero governance, attends public meetings, and reports on legislative decisions through EsteroToday.com. Terry Flanagan served as the community partner for this project, providing domain expertise on meeting structures, project categories, and the types of queries most valuable for civic transparency. Terry facilitated Zoom meetings with the team to clarify database requirements and helped define how ArcGIS StoryMaps could visualize meeting data for public consumption.

---

## Repository Structure

The repository as it actually exists today (the SQL/scraper/diagram folders
from earlier milestones have been superseded by the Python pipeline below):

```
EagleGIS/
|
|-- README.md                       # This file
|-- HANDOFF.md                      # Deep-dive maintainer guide for the data pipeline
|-- index.html                      # Public GitHub Pages site (parses the gold CSV)
|-- engage-estero-logo.png
|-- Makefile                        # Primary command surface (make help)
|-- Procfile                        # Process definition for deployment
|-- requirements.txt                # Python dependencies
|-- .pre-commit-config.yaml         # Rebuilds silver/gold on commit when bronze/reference change
|
|-- app/
|   |-- main.py                     # FastAPI app: mounts all routers + serves /dashboard
|   |-- static/dashboard.html       # Elderly-accessible interactive Leaflet map (served at /dashboard)
|   |-- config.py                   # API settings
|   |-- db.py                       # Supabase client (get_client, try_get_client)
|   |-- dependencies.py             # get_store() — single swap point for the data layer
|   |-- data/
|   |   |-- meetings.csv            # BRONZE  raw meeting rows
|   |   |-- documents.csv           # BRONZE  raw document rows
|   |   |-- minutes_index.json      # GENERATED  canonical PDF URLs from estero-fl.gov
|   |   |-- reference/*.yaml        # REFERENCE  projects, meeting_types, locations, geometries
|   |   |-- silver/                 # GENERATED  validated + cleaned CSVs (+ _rejects.json)
|   |   |-- gold/{meetings_public,meeting_actions_public}.csv  # GENERATED frontend/public CSVs
|   |   |-- extract/candidate_meetings.csv  # GENERATED proposed new meetings for PR review
|   |   |-- runs/                   # GENERATED  per-run manifests (gitignored)
|   |   |-- csv_store.py            # read-only store over silver/bronze (backs the JSON/GeoJSON API)
|   |   |-- mock.py                 # in-memory seed store (dead: get_store() returns CSVStore)
|   |-- pipeline/                   # THE PIPELINE  (bronze -> silver -> gold / Supabase)
|   |   |-- config.py               # filesystem paths, Estero bbox
|   |   |-- reference.py            # cached YAML loader
|   |   |-- collect/minutes.py      # scrape estero-fl.gov -> minutes_index.json
|   |   |-- extract/meetings.py     # discover newly-held meetings -> candidate_meetings.csv
|   |   |-- enrich/geocode.py       # optional US Census geocoder + cache
|   |   |-- clean/text.py           # OCR-artifact cleaner
|   |   |-- clean/actions.py        # structured action parser (kind/ref/amount)
|   |   |-- validate/schemas.py     # Pydantic models + FK checks
|   |   |-- load/silver.py          # bronze -> silver (+ minutes enrichment, synthesis)
|   |   |-- publish/gold.py         # silver+reference+docs+minutes -> gold public CSV
|   |   |-- publish/supabase.py     # silver+reference -> Supabase upsert
|   |   |-- verify/supabase.py      # Supabase -> drift report vs silver
|   |   |-- recover/cleanup_sql.py  # operator tool: emit "delete remote extras" SQL
|   |   |-- run.py                  # CLI orchestrator + run-manifest writer
|   |-- routers/
|   |   |-- export.py               # LIVE  Supabase-backed CSV exports for ArcGIS
|   |   |-- feature_service.py      # LIVE  Esri Feature Service endpoint
|   |   |-- {meetings,projects,documents,meeting_types,locations,layers}.py
|   |   |                           # MOUNTED  silver-backed JSON/GeoJSON read-API under /api/v1
|   |   |-- actions.py              # structured meeting-actions API (created, not mounted)
|   |-- services/geojson.py         # GeoJSON builders for the layers router
|   |-- models/                     # Pydantic API + GeoJSON schemas
|
|-- scripts/
|   |-- scrape_minutes_index.py     # CLI shim for the minutes collector
|   |-- scrape_meetings.py          # CLI shim for meetings discovery extractor
|
|-- tests/                          # pytest, no external credentials required
|
|-- .github/workflows/
    |-- ci.yml                      # tests + strict pipeline on every push/PR
    |-- publish.yml                 # publish + verify to Supabase (push to main, nightly, manual)
    |-- refresh-data.yml            # weekly: rescrape, rebuild silver+gold, commit, publish
    |-- discover-meetings.yml       # monthly: discover meetings and open candidate PR
    |-- drift-watch.yml             # read-only Supabase drift check every 6 hours
```

For a full tour of the pipeline (mental model, daily commands, recovering
from drift, and open issues), see **[HANDOFF.md](HANDOFF.md)**.

### Read-API and GIS layers (mounted)

The silver-backed JSON/GeoJSON read-API is now **mounted** under
`/api/v1`. It reads from the local silver CSVs (bronze fallback) via
`CSVStore`, so it works with **no Supabase credentials**:

- `GET /api/v1/meetings`, `/projects`, `/documents`, `/meeting-types`,
  `/locations` — typed JSON lists with optional filters, plus per-id
  detail endpoints that add cross-table context.
- `GET /api/v1/layers/points` / `/roads` / `/areas` — GeoJSON
  FeatureCollections for mapping. `points.csv` is also available for
  ArcGIS Online live layers.

Interactive docs are at `/docs`. The two original Supabase-backed routers
(`export`, `feature_service`) are unchanged.

### Interactive dashboard

A self-contained, **elderly-accessible** interactive map is served at
**`/dashboard`**. It uses Leaflet + OpenStreetMap and consumes the
mounted read-API on the same origin, so there are no CORS or build steps.

For GitHub Pages (static hosting), use **`dashboard.html`** at the repo
root. It preserves the same elderly-first UI and loads data directly from
`app/data/gold/meetings_public.csv` and reference YAML files.

Accessibility is a first-class requirement: large 18px+ rem-scaled text
with a "Text size" (A / A+ / A++) control, high-contrast colors meeting
WCAG AA, 44px+ click targets, plain-language labels, visible keyboard
focus outlines, ARIA landmarks, and a simple two-pane layout that
collapses to a single column on small screens. It shows project location
markers, the BERT Trail and Corkscrew Road corridors, a project filter, a
searchable meetings list with links to minutes PDFs, and summary stats.

Run it locally:

```bash
python -m uvicorn app.main:app --reload
# then open http://127.0.0.1:8000/dashboard
```

---

## Database Schema

The database consists of five BCNF-normalized tables hosted on Supabase (cloud PostgreSQL).

### Tables

**projects**
Stores metadata about Village of Estero infrastructure and policy projects.

| Column | Type | Constraints |
|--------|------|-------------|
| project_id | int4 | PRIMARY KEY |
| project_name | varchar | NOT NULL |
| description | text | |
| status | varchar | |

**meeting_types**
Classifies meetings by type (e.g., Regular Council Meeting, Public Hearing, Workshop).

| Column | Type | Constraints |
|--------|------|-------------|
| type_id | int4 | PRIMARY KEY |
| type_name | varchar | NOT NULL |
| description | text | |

**meetings**
Central table storing individual meeting records tied to projects and meeting types.

| Column | Type | Constraints |
|--------|------|-------------|
| meeting_id | int4 | PRIMARY KEY |
| project_id | int4 | FOREIGN KEY references projects(project_id) |
| type_id | int4 | FOREIGN KEY references meeting_types(type_id) |
| meeting_date | date | NOT NULL |
| meeting_year | int4 | NOT NULL |
| location | text | |
| start_time | varchar | |
| end_time | varchar | |
| action_taken | varchar | |
| status | varchar | |
| approved_by_council_date | date | |
| doc_ref_code | varchar | |
| filename | varchar | |
| notes | text | |

**documents**
Stores meeting-related documents such as agendas, minutes, and resolutions.

| Column | Type | Constraints |
|--------|------|-------------|
| document_id | int4 | PRIMARY KEY |
| meeting_id | int4 | FOREIGN KEY references meetings(meeting_id) |
| title | varchar | NOT NULL |
| document_type | varchar | |
| file_name | varchar | |
| file_url | text | |
| upload_date | date | |
| notes | text | |
| doc_date | date | |

**locations**
Stores geographic coordinates for project locations, enabling ArcGIS integration.

| Column | Type | Constraints |
|--------|------|-------------|
| location_id | int4 | PRIMARY KEY |
| project_id | int4 | FOREIGN KEY references projects(project_id) |
| location_name | varchar | |
| location_type | varchar | |
| address | text | |
| description | text | |
| latitude | numeric | |
| longitude | numeric | |

### Relationships

- One project has many meetings (projects 1:N meetings)
- One meeting has many documents (meetings 1:N documents)
- One meeting type classifies many meetings (meeting_types 1:N meetings)
- One project has many locations (projects 1:N locations)

### ER Diagram

See `diagrams/er_diagram.png` for the full Chen notation Entity-Relationship diagram showing all entities, attributes, and relationships.

### Relational Schema Diagram

See `diagrams/database_schema.png` for the relational schema showing table structures, data types, primary keys, and foreign key connections.

---

## Getting Started

### Prerequisites

- A Supabase account (free tier works): https://supabase.com
- Python 3.8 or higher (for the web scraper)
- A SQL client such as pgAdmin, DBeaver, or the Supabase SQL Editor
- Git

### Setting Up the Database

1. Clone the repository:

```bash
git clone https://github.com/your-username/estero-meetings-db.git
cd estero-meetings-db
```

2. Create a new Supabase project at https://supabase.com/dashboard. Note your project URL and API key.

3. Open the Supabase SQL Editor (or connect via pgAdmin using your Supabase connection string) and run the DDL script to create the tables:

```bash
# In the Supabase SQL Editor, paste and execute:
schema/create_tables.sql
```

4. Populate the database with the initial seed data:

```bash
# In the Supabase SQL Editor, paste and execute:
schema/seed_data.sql
```

5. Verify the tables were created and populated:

```sql
SELECT COUNT(*) FROM projects;
SELECT COUNT(*) FROM meetings;
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM meeting_types;
SELECT COUNT(*) FROM locations;
```

### Connecting to Supabase

Your Supabase connection details can be found under Project Settings > Database in the Supabase dashboard. You will need:

- Host: `db.<your-project-ref>.supabase.co`
- Port: `5432`
- Database: `postgres`
- User: `postgres`
- Password: Your database password (set during project creation)

---

## Web Scrapers / Collectors

The project now uses two stdlib-only collectors in the pipeline:

- `scripts/scrape_minutes_index.py` → canonical minutes PDF index at
  `app/data/minutes_index.json`
- `scripts/scrape_meetings.py` → proposed newly-held meetings at
  `app/data/extract/candidate_meetings.csv` (for PR review, not auto-import)

Both scrape estero-fl.gov pages and are covered by offline parser tests.
If the site structure changes, update selectors/patterns in
`app/pipeline/collect/minutes.py` and/or `app/pipeline/extract/meetings.py`.

---

## Populating the Database

### Using Seed Data

The `schema/seed_data.sql` file contains INSERT statements for the initial dataset, including records for the following Village of Estero projects:

- BERT Rail Trail
- Septic to Sewer Initiative
- Corkscrew Road Improvements

Run this file in the Supabase SQL Editor or through pgAdmin to populate the database.

### Adding New Records

To add new meeting records:

1. First ensure the associated project exists in the `projects` table. If not, insert it:

```sql
INSERT INTO projects (project_id, project_name, description, status)
VALUES (4, 'New Project Name', 'Description of the project', 'Active');
```

2. Ensure the meeting type exists in `meeting_types`. If not, insert it:

```sql
INSERT INTO meeting_types (type_id, type_name, description)
VALUES (5, 'Special Session', 'A specially called council session');
```

3. Insert the meeting record:

```sql
INSERT INTO meetings (meeting_id, project_id, type_id, meeting_date, meeting_year, location, start_time, action_taken, status)
VALUES (101, 4, 5, '2026-03-15', 2026, 'Estero Village Hall', '5:30 PM', 'Approved', 'Completed');
```

4. Insert any associated documents:

```sql
INSERT INTO documents (document_id, meeting_id, title, document_type, file_url, doc_date)
VALUES (201, 101, 'Meeting Minutes - March 15 2026', 'Minutes', 'https://estero-fl.gov/docs/minutes-031526.pdf', '2026-03-15');
```

5. If the project has a physical location, add it to the `locations` table with latitude and longitude:

```sql
INSERT INTO locations (location_id, project_id, location_name, location_type, address, latitude, longitude)
VALUES (10, 4, 'Project Site', 'Construction Zone', '123 Main St, Estero, FL', 26.4381, -81.8068);
```

---

## Running Queries

The `queries/` directory contains pre-written SQL queries organized by use case. Below are some key examples.

### Filter Meetings by Project

```sql
SELECT m.meeting_id, m.meeting_date, m.action_taken, m.status, p.project_name
FROM meetings m
JOIN projects p ON m.project_id = p.project_id
WHERE p.project_name = 'BERT Rail Trail'
ORDER BY m.meeting_date;
```

### Find Documents for a Specific Meeting

```sql
SELECT d.title, d.document_type, d.file_url, d.doc_date
FROM documents d
WHERE d.meeting_id = 1
ORDER BY d.doc_date;
```

### Track All Meetings for a Project Chronologically

```sql
SELECT m.meeting_date, mt.type_name, m.action_taken, m.status, m.notes
FROM meetings m
JOIN meeting_types mt ON m.type_id = mt.type_id
WHERE m.project_id = 1
ORDER BY m.meeting_date ASC;
```

### Find Meetings Where Council Approved Action

```sql
SELECT m.meeting_date, p.project_name, m.action_taken, m.approved_by_council_date
FROM meetings m
JOIN projects p ON m.project_id = p.project_id
WHERE m.approved_by_council_date IS NOT NULL
ORDER BY m.approved_by_council_date;
```

### Count Meetings Per Project

```sql
SELECT p.project_name, COUNT(m.meeting_id) AS total_meetings
FROM projects p
LEFT JOIN meetings m ON p.project_id = m.project_id
GROUP BY p.project_name
ORDER BY total_meetings DESC;
```

---

## ArcGIS Export

The database is designed with geospatial readiness in mind. The `locations` table stores latitude and longitude coordinates for each project location, enabling direct export to ArcGIS StoryMaps.

### Generating the CSV Export

Run the following query to generate an ArcGIS-compatible CSV:

```sql
SELECT
    p.project_name,
    p.description AS project_description,
    p.status AS project_status,
    m.meeting_date,
    m.meeting_year,
    mt.type_name AS meeting_type,
    m.action_taken,
    m.status AS meeting_status,
    l.location_name,
    l.address,
    l.latitude,
    l.longitude
FROM meetings m
JOIN projects p ON m.project_id = p.project_id
JOIN meeting_types mt ON m.type_id = mt.type_id
JOIN locations l ON p.project_id = l.project_id
ORDER BY p.project_name, m.meeting_date;
```

In the Supabase SQL Editor, run this query and download the results as CSV. In pgAdmin, you can use the "Export" option or the `\copy` command.

### Importing into ArcGIS

1. Open ArcGIS Online or ArcGIS StoryMaps.
2. Add a new layer and select "Add layer from file."
3. Upload the exported CSV file.
4. ArcGIS will automatically detect the `latitude` and `longitude` columns and plot the locations on the map.
5. Configure pop-ups to display project name, meeting date, action taken, and status for each point.

### Notes

- Ensure latitude and longitude values are in decimal degrees (WGS 84 coordinate system), which is the standard for ArcGIS.
- All coordinates in the database should reference locations within or near the Village of Estero, Florida (approximate center: 26.44 N, -81.81 W).
- If a project spans multiple locations, each location gets its own row in the `locations` table with a separate `location_id` but the same `project_id`.

---

## Maintenance Guide for Future Teams

This section is written for anyone who picks up this project in a future semester. Here is what you need to know.

### Understanding the Current State

- The database is hosted on Supabase. You will need access credentials from the previous team or from Dr. Ahuja. If credentials are unavailable, you can create a new Supabase project and re-run the DDL and seed scripts from this repository.
- The current dataset covers three major Village of Estero projects: BERT Rail Trail, Septic to Sewer, and Corkscrew Road. These were selected in collaboration with Terry Flanagan as representative examples.
- The web scraper was built to extract data from the Village of Estero website as it existed during Spring 2026. Website structures change, so the scraper may require updates.

### Expanding the Database

The most impactful next step is expanding coverage to include all Village of Estero public meeting records from 2014 (incorporation) to the present. To do this:

1. Identify all meeting types held by the Village (council meetings, planning and zoning boards, design review boards, etc.) and ensure they exist in the `meeting_types` table.
2. For each new project the Village discusses, add a row to the `projects` table.
3. Scrape or manually collect meeting records and insert them into the `meetings` and `documents` tables.
4. For projects with physical locations, geocode the addresses to get latitude and longitude and add them to the `locations` table. Google Maps or the US Census Geocoder (https://geocoding.geo.census.gov/geocoder/) can be used for this.

### Keeping the Minutes Collector Updated

- The minutes collector (`app/pipeline/collect/minutes.py`) scrapes the
  Village Council and PZDB minutes index pages on estero-fl.gov for PDF
  links and parses meeting dates out of the filenames. If the Village
  changes its page structure or the PDF upload path, update `SOURCES` and
  `PDF_RE` at the top of that module, plus the date patterns if filenames
  change format.
- The pure parsing helpers are unit-tested in
  `tests/test_minutes_collector.py` (no network), so you can add a failing
  case for any new filename format before fixing the regex.
- The weekly `refresh-data.yml` workflow runs the collector automatically;
  watch the run summary for the count of skipped (undated) filenames.

### Working with Terry Flanagan and Engage Estero

- Terry Flanagan (Engage Estero / EsteroToday.com) is the community partner for this project. He can provide context on which projects are most important to track, what types of queries Estero residents would find most useful, and how the ArcGIS StoryMap should be designed for public consumption.
- Previous communication with Terry was conducted via Zoom and email. He is responsive and knowledgeable about Village governance.
- Kim Dailey was the ArcGIS contact who can assist with StoryMap configuration and best practices.

### Already done since the original milestone

- **Public search UI** — `index.html` ships an in-browser MiniSearch
  full-text index over the gold CSV (BM25, prefix + light fuzziness), so a
  separate Postgres `tsvector` search isn't needed for the public site.
- **Scheduled refresh** — `.github/workflows/refresh-data.yml` rescrapes the
  minutes index, rebuilds silver + gold, commits the artifacts, and
  republishes to Supabase weekly (plus manual dispatch).
- **Canonical PDF links** — the minutes collector + silver enrichment replace
  guessed links with authoritative estero-fl.gov PDFs.

### Potential Future Enhancements

- ~~Add a meetings scraper (not just minutes)~~ **Done (proposal stage)** —
  monthly `discover-meetings.yml` opens candidate PRs via
  `app/data/extract/candidate_meetings.csv`.
- ~~Structure `action_taken` into a real `meeting_actions` table~~ **Done** —
  silver + gold action feeds are generated (`meeting_actions.csv`,
  `meeting_actions_public.csv`).
- ~~Add a geocoding stage (`app/pipeline/enrich/geocode.py`)~~ **Done
  (optional stage)** — with JSON cache; currently a no-op for committed data.
- Expand `locations.yaml` coverage; council meetings without a mapped
  location currently get blank `Latitude/Longitude` in the gold CSV.
- ~~Mount the silver-backed JSON/GeoJSON read-API (HANDOFF.md issue #5)~~
  **Done** — the read-API is mounted under `/api/v1` and an
  elderly-accessible interactive dashboard is served at `/dashboard`.
  A GitHub Pages-compatible static version is available at
  `dashboard.html`. Next: tighten CORS for production and expand dashboard
  filtering (for example date ranges and actions).
- Create user roles / access controls in Supabase if multiple volunteers
  will be entering data.

---

## Technologies Used

| Technology | Purpose |
|------------|---------|
| PostgreSQL | Relational database engine |
| Supabase | Cloud-hosted PostgreSQL platform with dashboard and REST API |
| Python | Web scraping and data processing |
| SQL | Query development, data analysis, and export |
| ArcGIS StoryMaps | Geospatial visualization for public-facing map |
| Git / GitHub | Version control and project handoff |

---

## License

This project was developed for academic purposes as part of COP 3710 - Database Systems at Florida Gulf Coast University. It is intended for use by Engage Estero and future FGCU student teams continuing this work. Please contact the team or Dr. Vinod Ahuja for questions about usage and permissions.
