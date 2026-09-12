"""Unit tests for pipeline validation schemas."""
import pytest

from app.pipeline.validate.schemas import (
    DocumentRow,
    LocationRow,
    MeetingRow,
    validate_rows,
)


def _good_meeting_row() -> dict:
    return {
        "meeting_id": "1",
        "project_id": "1",
        "type_id": "1",
        "meeting_date": "2024-01-03",
        "meeting_year": "2024",
        "location": "Village of Estero Council Chambers",
        "start_time": "9:30 AM",
        "end_time": "null",
        "action_taken": "Adopted Resolution No. 2024-01.",
        "status": "",
        "approved_by_council_date": "null",
        "doc_ref_code": "td/CS",
        "filename": "01032024 minutes.pdf",
        "notes": "null",
        "location_id": "null",
    }


def test_meeting_row_coerces_csv_strings():
    row = MeetingRow.model_validate(_good_meeting_row())
    assert row.meeting_id == 1
    assert row.meeting_year == 2024
    assert row.end_time is None
    assert row.status == "Accepted"


def test_meeting_year_must_match_meeting_date():
    bad = _good_meeting_row() | {"meeting_year": "2023"}
    valid, rejects = validate_rows([bad], MeetingRow)
    assert not valid
    assert rejects and "meeting_year 2023 does not match" in rejects[0]["errors"][0]


def test_unknown_project_id_rejected():
    bad = _good_meeting_row() | {"project_id": "999"}
    valid, rejects = validate_rows([bad], MeetingRow)
    assert not valid
    assert any("unknown project_id=999" in e for e in rejects[0]["errors"])


def test_unknown_type_id_rejected():
    bad = _good_meeting_row() | {"type_id": "999"}
    valid, rejects = validate_rows([bad], MeetingRow)
    assert not valid


def test_unknown_location_id_rejected():
    bad = _good_meeting_row() | {"location_id": "999"}
    valid, rejects = validate_rows([bad], MeetingRow)
    assert not valid
    assert any("unknown location_id=999" in e for e in rejects[0]["errors"])


def test_location_row_outside_bbox_rejected():
    bad_location = {
        "location_id": 1,
        "project_id": 1,
        "location_name": "Outside",
        "latitude": 28.0,
        "longitude": -81.8,
    }
    valid, rejects = validate_rows([bad_location], LocationRow)
    assert not valid
    assert any("outside ESTERO_BBOX" in e for e in rejects[0]["errors"])


def test_document_row_accepts_minimal():
    row = DocumentRow.model_validate({
        "document_id": "10",
        "meeting_id": "5",
        "title": "",
        "doc_date": "2024-03-15",
    })
    assert row.title == "Untitled"
    assert row.doc_date.isoformat() == "2024-03-15"


def test_validate_rows_returns_both_valid_and_rejects():
    rows = [_good_meeting_row(), _good_meeting_row() | {"meeting_id": "not-an-int"}]
    valid, rejects = validate_rows(rows, MeetingRow)
    assert len(valid) == 1
    assert len(rejects) == 1
