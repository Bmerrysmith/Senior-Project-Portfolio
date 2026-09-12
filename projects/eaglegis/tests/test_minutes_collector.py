"""
Tests for the minutes collector (``app/pipeline/collect/minutes.py``).

The collector's network fetch is intentionally not exercised here; these
tests pin down the pure parsing/resolution helpers so the index stays
correct as estero-fl.gov filenames vary.
"""
from __future__ import annotations

from app.pipeline.collect.minutes import (
    build_section,
    extract_pdfs,
    iso_date_from_filename,
    load_minutes_index,
    minutes_body_key,
    resolve_minutes_url,
)


def test_iso_date_from_filename_common_formats():
    assert iso_date_from_filename("12092025 PZDB Minutes.pdf") == "2025-12-09"
    assert iso_date_from_filename("2025-12-09 Council Minutes.pdf") == "2025-12-09"
    assert iso_date_from_filename("December 9, 2025 Minutes.pdf") == "2025-12-09"
    assert iso_date_from_filename("20251209-minutes.pdf") == "2025-12-09"


def test_iso_date_from_filename_two_digit_year():
    assert iso_date_from_filename("030124 Minutes.pdf") == "2024-03-01"


def test_iso_date_from_filename_skips_cancellations_and_garbage():
    assert iso_date_from_filename("Cancellation Notice.pdf") is None
    assert iso_date_from_filename("Meeting Rescheduled.pdf") is None
    assert iso_date_from_filename("agenda-overview.pdf") is None


def test_extract_pdfs_dedupes_and_filters_to_minutes_path():
    html = """
      <a href="https://estero-fl.gov/wp-content/uploads/library-ada/minutes/A.pdf">A</a>
      <a href="https://estero-fl.gov/wp-content/uploads/library-ada/minutes/A.pdf">dup</a>
      <a href="https://estero-fl.gov/wp-content/uploads/library-ada/minutes/B.pdf">B</a>
      <a href="https://estero-fl.gov/some/other/file.pdf">ignored</a>
    """
    urls = extract_pdfs(html)
    assert urls == [
        "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/A.pdf",
        "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/B.pdf",
    ]


def test_build_section_prefers_approved_over_draft_for_same_date():
    base = "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/"
    html = (
        f'<a href="{base}03012024%20Draft%20Minutes.pdf"></a>'
        f'<a href="{base}03012024%20Approved%20Minutes.pdf"></a>'
    )
    mapping, skipped = build_section(html)
    assert mapping["2024-03-01"].endswith("Approved%20Minutes.pdf")
    assert skipped == []


def test_build_section_records_undated_files_as_skipped():
    base = "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/"
    html = f'<a href="{base}Cancellation.pdf"></a>'
    mapping, skipped = build_section(html)
    assert mapping == {}
    assert skipped == ["Cancellation.pdf"]


def test_minutes_body_key_routing():
    assert minutes_body_key("Planning Zoning & Design Board", type_id=2) == "pzdb"
    assert minutes_body_key(None, type_id=2) == "pzdb"
    assert minutes_body_key("Village Council", type_id=1) == "council"
    assert minutes_body_key(None) == "council"


def test_resolve_minutes_url_by_body_and_date():
    index = {
        "council": {"2025-01-02": "https://x/council.pdf"},
        "pzdb": {"2025-01-02": "https://x/pzdb.pdf"},
    }
    assert resolve_minutes_url(index, "2025-01-02", type_id=1) == "https://x/council.pdf"
    assert resolve_minutes_url(index, "2025-01-02", type_id=2) == "https://x/pzdb.pdf"
    assert resolve_minutes_url(index, "2025-01-02T00:00:00", type_id=1) == "https://x/council.pdf"
    assert resolve_minutes_url(index, "1999-01-01", type_id=1) is None
    assert resolve_minutes_url(index, "", type_id=1) is None


def test_load_minutes_index_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "nope.json"
    idx = load_minutes_index(missing)
    assert idx == {"council": {}, "pzdb": {}, "_meta": {}}
