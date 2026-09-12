"""Tests for in-progress meeting classification (``app/pipeline/extract/in_progress.py``)."""
from __future__ import annotations

import csv

from app.pipeline.extract import in_progress as P


def test_pzdb_documents_marked_in_progress_when_mapping_active():
    state, reasons, _desc = P.assess_progress(
        body="pzdb",
        meeting_date="2024-06-11",
        status="Accepted",
        link_status="Uploaded",
        project_id=4,
        bronze_source_file="documents.csv",
        pzdb_mapping_active=True,
    )
    assert state == P.PROGRESS_IN_PROGRESS
    assert P.REASON_PZDB_PROJECT_MAPPING in reasons


def test_council_meeting_not_in_progress_without_flags():
    state, reasons, _desc = P.assess_progress(
        body="council",
        meeting_date="2024-01-03",
        status="Accepted",
        link_status="",
        project_id=2,
        bronze_source_file="meetings.csv",
        pzdb_mapping_active=True,
    )
    assert state == P.PROGRESS_COMPLETE
    assert reasons == []


def test_future_placeholder_and_pending():
    state, reasons, _desc = P.assess_progress(
        body="pzdb",
        meeting_date="2026-12-08",
        status="Pending",
        link_status="Future Placeholder",
        bronze_source_file="documents.csv",
        pzdb_mapping_active=True,
    )
    assert state == P.PROGRESS_IN_PROGRESS
    assert P.REASON_FUTURE_PLACEHOLDER in reasons
    assert P.REASON_PENDING_STATUS in reasons


def test_cancelled_is_closed_not_in_progress():
    state, reasons, desc = P.assess_progress(
        body="council",
        meeting_date="2026-01-21",
        status="Cancelled",
        bronze_source_file="meetings.csv",
    )
    assert state == P.PROGRESS_CLOSED
    assert reasons == []
    assert "cancelled" in desc.lower()


def test_gold_columns_yes_with_note(monkeypatch):
    monkeypatch.setattr(P, "pzdb_project_mapping_in_progress", lambda: True)
    meeting = {
        "project_id": 4,
        "type_id": 2,
        "meeting_date": "2025-06-10",
        "status": "Accepted",
    }
    doc = {"type_name": "Planning Zoning & Design Board", "link_status": "Uploaded"}
    yes_no, note = P.gold_in_progress_columns(meeting, doc)
    assert yes_no == "Yes"
    assert "PZ&DB" in note


def test_collect_in_progress_meetings_writes_csv(tmp_path, monkeypatch):
    meetings = tmp_path / "meetings.csv"
    documents = tmp_path / "documents.csv"
    meetings.write_text(
        "meeting_id,project_id,type_id,meeting_date,status,link_status\n"
        "1,1,1,2024-01-03,Accepted,\n",
        encoding="utf-8",
    )
    documents.write_text(
        "document_id,meeting_id,meeting_date,status,type_name,link_status\n"
        "10,10,2026-12-08,Pending,Planning Zoning & Design Board,Future Placeholder\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(P.config, "BRONZE_MEETINGS", meetings)
    monkeypatch.setattr(P.config, "BRONZE_DOCUMENTS", documents)
    out = tmp_path / "in_progress_meetings.csv"
    report = P.collect_in_progress_meetings(out_path=out)

    assert report["total_bronze_rows"] == 2
    assert report["in_progress"] == 1
    assert report["complete"] == 1
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["progress_state"] == P.PROGRESS_IN_PROGRESS
    assert "future_placeholder" in rows[0]["in_progress_reasons"]
