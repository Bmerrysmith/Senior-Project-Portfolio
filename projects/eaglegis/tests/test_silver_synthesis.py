"""
Tests for the silver build's "derived meetings from documents" step.

The bronze documents feed describes PZ&DB meetings that don't appear in
the bronze meetings feed (which is Village Council only). To keep
documents FK-valid against the meetings table, silver synthesizes one
meeting per document ``meeting_id``. These tests pin down that behaviour
so it doesn't silently regress.
"""
from __future__ import annotations

import csv
import json

from app.pipeline import config
from app.pipeline.load.silver import (
    SYNTHESIZED_MEETING_DEFAULTS,
    SYNTHESIZED_MEETING_LOCATION_NAME,
    _filename_from_url,
    _synthesize_pzdb_meetings_from_documents,
    build_silver,
)


def _silver_meetings() -> list[dict]:
    with open(config.SILVER_MEETINGS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _silver_rejects() -> dict:
    return json.loads(config.SILVER_REJECTS.read_text())


def test_filename_from_url_unquotes_and_handles_empty():
    assert _filename_from_url(
        "https://example.com/files/12092025%20PZDB%20Minutes.pdf"
    ) == "12092025 PZDB Minutes.pdf"
    assert _filename_from_url("") is None
    assert _filename_from_url(None) is None


def test_synthesize_emits_one_meeting_per_unknown_meeting_id():
    from datetime import date
    docs = [
        {"meeting_id": 201, "meeting_date": date(2025, 1, 1), "meeting_year": 2025,
         "type_name": "Planning Zoning & Design Board",
         "file_url": "https://x/y/A.pdf", "status": "Pending"},
        # duplicate meeting_id collapses to a single synth row
        {"meeting_id": 201, "meeting_date": date(2025, 1, 1), "meeting_year": 2025,
         "type_name": "Planning Zoning & Design Board",
         "file_url": "https://x/y/A-attachment.pdf", "status": "Pending"},
        {"meeting_id": 202, "meeting_date": date(2025, 2, 5), "meeting_year": 2025,
         "type_name": "Planning Zoning & Design Board",
         "file_url": "https://x/y/B.pdf", "status": "Pending"},
    ]
    synth, rejects = _synthesize_pzdb_meetings_from_documents(docs, existing_meeting_ids=set())
    assert [m["meeting_id"] for m in synth] == [201, 202]
    assert rejects == []
    # Defaults match the SYNTHESIZED_MEETING_DEFAULTS table.
    pzdb = SYNTHESIZED_MEETING_DEFAULTS["Planning Zoning & Design Board"]
    for m in synth:
        assert m["type_id"] == pzdb["type_id"]
        assert m["project_id"] == pzdb["project_id"]
        assert m["location_id"] == pzdb["location_id"]
        assert m["location"] == SYNTHESIZED_MEETING_LOCATION_NAME
        assert m["status"] == "Accepted"
        assert m["notes"].startswith("Derived from document feed")


def test_synthesize_skips_existing_meeting_ids():
    from datetime import date
    docs = [
        {"meeting_id": 50, "meeting_date": date(2024, 1, 1), "meeting_year": 2024,
         "type_name": "Planning Zoning & Design Board",
         "file_url": "https://x/y.pdf", "status": "Pending"},
    ]
    synth, rejects = _synthesize_pzdb_meetings_from_documents(docs, existing_meeting_ids={50})
    assert synth == []
    assert rejects == []


def test_synthesize_rejects_unknown_type_name():
    from datetime import date
    docs = [
        {"meeting_id": 999, "meeting_date": date(2024, 1, 1), "meeting_year": 2024,
         "type_name": "School Board", "file_url": None, "status": None},
    ]
    synth, rejects = _synthesize_pzdb_meetings_from_documents(docs, existing_meeting_ids=set())
    assert synth == []
    assert len(rejects) == 1
    assert "unknown type_name" in rejects[0]["errors"][0]


def test_synthesize_rejects_missing_meeting_date():
    docs = [
        {"meeting_id": 999, "meeting_date": None, "meeting_year": 2024,
         "type_name": "Planning Zoning & Design Board",
         "file_url": "https://x/y.pdf", "status": None},
    ]
    synth, rejects = _synthesize_pzdb_meetings_from_documents(docs, existing_meeting_ids=set())
    assert synth == []
    assert len(rejects) == 1
    assert "meeting_date is empty" in rejects[0]["errors"][0]


def test_synthesize_filename_is_urldecoded_basename():
    from datetime import date
    docs = [
        {"meeting_id": 300, "meeting_date": date(2024, 6, 1), "meeting_year": 2024,
         "type_name": "Planning Zoning & Design Board",
         "file_url": "https://estero-fl.gov/files/06012024%20PZDB%20Minutes.pdf",
         "status": "Pending"},
    ]
    synth, _ = _synthesize_pzdb_meetings_from_documents(docs, existing_meeting_ids=set())
    assert synth[0]["filename"] == "06012024 PZDB Minutes.pdf"


# ---------------------------------------------------------------------------
# End-to-end: real bronze data
# ---------------------------------------------------------------------------

def test_build_silver_eliminates_document_fk_warnings():
    """Against the real bronze CSVs, every document's meeting_id is now
    backed by either a bronze or a synthesized meeting."""
    report = build_silver()
    assert report["documents"]["fk_warnings"] == 0
    assert report["meetings"]["out_synthesized"] >= 1
    assert (
        report["meetings"]["out"]
        == report["meetings"]["out_bronze"] + report["meetings"]["out_synthesized"]
    )

    meetings = _silver_meetings()
    meeting_ids = {int(m["meeting_id"]) for m in meetings}
    with open(config.SILVER_DOCUMENTS, newline="", encoding="utf-8") as f:
        for d in csv.DictReader(f):
            assert int(d["meeting_id"]) in meeting_ids, (
                f"document {d['document_id']} references missing meeting "
                f"{d['meeting_id']}"
            )


def test_build_silver_synthesized_rows_have_pzdb_defaults():
    build_silver()
    synth = [m for m in _silver_meetings() if (m["notes"] or "").startswith("Derived")]
    assert synth, "expected at least one synthesized PZ&DB meeting"
    for m in synth:
        assert m["type_id"] == "2"
        assert m["project_id"] == "4"
        assert m["location_id"] == "6"
        assert m["location"] == SYNTHESIZED_MEETING_LOCATION_NAME
        assert m["filename"], "synth row should derive filename from file_url"
