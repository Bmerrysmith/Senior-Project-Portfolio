"""
Tests for the gold-layer public CSV builder (``app/pipeline/publish/gold.py``).

The gold builder denormalizes silver + reference + documents into the exact
public schema the GitHub Pages frontend (``index.html``) parses. These
tests lock the schema and the join behaviour so the public site never
silently breaks.
"""
from __future__ import annotations

import csv

from app.pipeline import config
from app.pipeline.load.silver import build_silver
from app.pipeline.publish.gold import (
    GOLD_FIELDS,
    _documents_by_meeting,
    _fmt_coord,
    _meeting_finalized,
    _meeting_type_display,
    _resolve_location,
    build_gold,
)


def _read_gold() -> list[dict]:
    with open(config.GOLD_MEETINGS_PUBLIC, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_fmt_coord_handles_blanks_and_floats():
    assert _fmt_coord(None) == ""
    assert _fmt_coord("") == ""
    assert _fmt_coord("26.4381") == "26.4381"
    assert _fmt_coord(26.4381) == "26.4381"
    assert _fmt_coord("not-a-number") == "not-a-number"


def test_meeting_type_display_maps_known_and_passes_through():
    assert _meeting_type_display("Village Council") == "Regular Council Meeting"
    assert _meeting_type_display("Planning Zoning & Design Board") == "PZDB Meeting"
    assert _meeting_type_display("Something Else") == "Something Else"
    assert _meeting_type_display("") == "Other"


def test_documents_by_meeting_prefers_uploaded():
    docs = [
        {"meeting_id": 1, "file_url": "a", "link_status": "Missing / Not Uploaded"},
        {"meeting_id": 1, "file_url": "b", "link_status": "Uploaded"},
        {"meeting_id": 2, "file_url": "c", "link_status": "Uploaded"},
    ]
    best = _documents_by_meeting(docs)
    assert best[1]["file_url"] == "b"
    assert best[2]["file_url"] == "c"


def test_resolve_location_by_location_id():
    loc_by_id = {6: {"location_name": "Council Chambers", "latitude": 26.4, "longitude": -81.8}}
    meeting = {"location_id": 6, "project_id": 4}
    name, lat, lon, confidence = _resolve_location(meeting, loc_by_id, {})
    assert name == "Council Chambers"
    assert lat == "26.4"
    assert lon == "-81.8"
    assert confidence == "exact_location_id"


def test_resolve_location_falls_back_to_project_then_text():
    locs_by_project = {4: [{"location_id": 9, "location_name": "Proj Loc", "latitude": 26.5, "longitude": -81.7}]}
    by_project = _resolve_location({"project_id": 4, "location": "x"}, {}, locs_by_project)
    assert by_project == ("Proj Loc", "26.5", "-81.7", "project_fallback")

    text_only = _resolve_location({"location": "Somewhere"}, {}, {})
    assert text_only == ("Somewhere", "", "", "text_only")


# ---------------------------------------------------------------------------
# End-to-end: real silver + reference data
# ---------------------------------------------------------------------------

def test_meeting_finalized_labels():
    assert _meeting_finalized("Accepted", "https://estero-fl.gov/x.pdf") == "Yes"
    assert _meeting_finalized("Accepted", "") == "No"
    assert _meeting_finalized("Cancelled", "https://estero-fl.gov/x.pdf") == "Cancelled"


def test_build_gold_emits_exact_schema_and_all_rows():
    silver_report = build_silver()
    report = build_gold()

    assert config.GOLD_MEETINGS_PUBLIC.exists()
    rows = _read_gold()

    # One gold row per silver meeting.
    assert report["rows"] == len(rows) == silver_report["meetings"]["out"]

    # Header is exactly the frontend contract, in order.
    with open(config.GOLD_MEETINGS_PUBLIC, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == GOLD_FIELDS


def test_build_gold_emits_json_and_site_manifest():
    build_silver()
    report = build_gold()

    assert config.GOLD_MEETINGS_JSON.exists()
    assert config.GOLD_SITE_MANIFEST.exists()
    assert report["json_path"] == "app/data/gold/meetings_public.json"
    assert report["manifest_path"] == "app/data/gold/site_manifest.json"
    assert report["delivery"] == "monolith"

    import json

    json_rows = json.loads(config.GOLD_MEETINGS_JSON.read_text(encoding="utf-8"))
    csv_rows = _read_gold()
    assert len(json_rows) == len(csv_rows) == report["rows"]

    manifest = json.loads(config.GOLD_SITE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["version"] >= 2
    assert manifest["primary"] == "arcgis"
    assert manifest["arcgis"]["rows"] > 0
    assert manifest["meetings"]["rows"] == report["rows"]
    assert manifest["meetings"]["sha256"]
    assert manifest["meetings"]["json"] == "app/data/gold/meetings_public.json"
    assert manifest["meetings"]["shards"] is None


def test_build_gold_emits_year_shards_when_threshold_low(monkeypatch):
    monkeypatch.setattr(config, "GOLD_SHARD_THRESHOLD", 1)
    build_silver()
    report = build_gold()

    assert report["delivery"] == "sharded"
    assert report["shards"] >= 1

    import json

    manifest = json.loads(config.GOLD_SITE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["delivery"] == "sharded"
    assert manifest["meetings"]["shards"]
    for shard in manifest["meetings"]["shards"]:
        shard_path = config.DATA_DIR.parent.parent / shard["path"]
        assert shard_path.exists()
        assert shard["rows"] >= 1


def test_build_gold_rows_are_sorted_newest_first():
    build_silver()
    build_gold()
    rows = _read_gold()
    dates = [r["MeetingDate"] for r in rows]
    assert dates == sorted(dates, reverse=True)


def test_build_gold_populates_minutes_urls_and_coords():
    build_silver()
    report = build_gold()
    rows = _read_gold()

    assert report["with_minutes_url"] >= 1
    assert any(r["MinutesURL"].startswith("http") for r in rows)
    assert all(r["Finalized"] in {"Yes", "No", "Cancelled"} for r in rows)
    assert all(r["InProgress"] in {"Yes", "No"} for r in rows)
    assert sum(1 for r in rows if r["Finalized"] == "No") == 4
    assert sum(1 for r in rows if r["InProgress"] == "Yes") >= 76
    # PZ&DB synthesized meetings map to Council Chambers (location_id 6),
    # which carries coordinates in locations.yaml.
    assert any(r["Latitude"] and r["Longitude"] for r in rows)
    assert "location_quality" in report
    assert report["location_quality"]["with_coords"] >= 1
