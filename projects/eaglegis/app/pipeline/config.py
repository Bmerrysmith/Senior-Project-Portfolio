"""
Single source of truth for pipeline filesystem paths.

Importing this module is cheap; nothing here touches disk.
"""
from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPO_ROOT = DATA_DIR.parent.parent

BRONZE_DIR = DATA_DIR
REFERENCE_DIR = DATA_DIR / "reference"
SILVER_DIR = DATA_DIR / "silver"
RUNS_DIR = DATA_DIR / "runs"

BRONZE_MEETINGS = BRONZE_DIR / "meetings.csv"
BRONZE_DOCUMENTS = BRONZE_DIR / "documents.csv"

SILVER_MEETINGS = SILVER_DIR / "meetings.csv"
SILVER_DOCUMENTS = SILVER_DIR / "documents.csv"
SILVER_DOCUMENTS_PLANNED = SILVER_DIR / "documents_planned.csv"
SILVER_MEETING_ACTIONS = SILVER_DIR / "meeting_actions.csv"
SILVER_REJECTS = SILVER_DIR / "_rejects.json"

GOLD_DIR = DATA_DIR / "gold"
GOLD_MEETINGS_PUBLIC = GOLD_DIR / "meetings_public.csv"
GOLD_MEETINGS_JSON = GOLD_DIR / "meetings_public.json"
GOLD_SITE_MANIFEST = GOLD_DIR / "site_manifest.json"
GOLD_SHARDS_DIR = GOLD_DIR / "shards"
GOLD_MEETING_ACTIONS_PUBLIC = GOLD_DIR / "meeting_actions_public.csv"
GOLD_AI_PUBLIC = GOLD_DIR / "meetings_ai_public.csv"
GOLD_AI_JSONL = GOLD_DIR / "meetings_ai_public.jsonl"
GOLD_ARCGIS_PUBLIC = GOLD_DIR / "arcgis_agenda_map_data.csv"

# Normalized extraction inputs for the AI gold layer (agenda-item grain).
NORMALIZED_COUNCIL_DIR = REPO_ROOT / "normalized_csv_council"
NORMALIZED_PZDB_DIR = REPO_ROOT / "normalized_csv_pilot" / "pzdb_from_raw_verify"

# When public meeting rows reach this count, gold also emits per-year JSON shards
# so the GitHub Pages frontend can fetch data incrementally.
GOLD_SHARD_THRESHOLD = 500

MINUTES_INDEX = DATA_DIR / "minutes_index.json"

EXTRACT_DIR = DATA_DIR / "extract"
CANDIDATE_MEETINGS = EXTRACT_DIR / "candidate_meetings.csv"
IN_PROGRESS_MEETINGS = EXTRACT_DIR / "in_progress_meetings.csv"

REF_PROJECTS = REFERENCE_DIR / "projects.yaml"
REF_MEETING_TYPES = REFERENCE_DIR / "meeting_types.yaml"
REF_LOCATIONS = REFERENCE_DIR / "locations.yaml"
REF_GEOMETRIES = REFERENCE_DIR / "geometries.yaml"

# Cache of geocoder responses keyed by query address (see app/pipeline/enrich/geocode.py).
GEOCODE_CACHE = REFERENCE_DIR / "geocode_cache.json"

ESTERO_BBOX = {
    "min_lat": 26.30,
    "max_lat": 26.55,
    "min_lon": -81.95,
    "max_lon": -81.65,
}

# Maximum allowed drift between canonical coordinates and a fresh Census
# geocode lookup before strict mode fails the run.
GEOCODE_MISMATCH_THRESHOLD_METERS = 1000.0

FUTURE_PLACEHOLDER_TAG = "Future Placeholder"
