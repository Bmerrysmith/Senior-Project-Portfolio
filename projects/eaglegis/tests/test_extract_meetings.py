"""
Tests for the meetings-discovery extractor (``app/pipeline/extract/meetings.py``).

These are credential-free and NETWORK-FREE: the parsing functions are pure and
fed HTML/strings directly, and ``collect_candidate_meetings`` is exercised with
``fetch`` monkeypatched so nothing ever touches the network.
"""
from __future__ import annotations

from app.pipeline.extract import meetings as M

BASE = "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/"


# --------------------------------------------------------------------------- #
# parse_meeting_date / normalize_iso
# --------------------------------------------------------------------------- #
def test_parse_meeting_date_common_formats():
    assert M.parse_meeting_date("12092025 PZDB Minutes.pdf") == "2025-12-09"
    assert M.parse_meeting_date("2025-12-09 Council Minutes.pdf") == "2025-12-09"
    assert M.parse_meeting_date("December 9, 2025 Minutes.pdf") == "2025-12-09"
    assert M.parse_meeting_date("20251209-minutes.pdf") == "2025-12-09"
    assert M.parse_meeting_date("Council Meeting 1/13/2026") == "2026-01-13"


def test_parse_meeting_date_two_digit_year():
    assert M.parse_meeting_date("030124 Minutes.pdf") == "2024-03-01"


def test_parse_meeting_date_skips_cancellations_and_garbage():
    assert M.parse_meeting_date("Cancellation Notice 01032024.pdf") is None
    assert M.parse_meeting_date("Meeting Rescheduled 01032024.pdf") is None
    assert M.parse_meeting_date("agenda-overview.pdf") is None
    assert M.parse_meeting_date("") is None


def test_parse_meeting_date_rejects_impossible_dates():
    assert M.parse_meeting_date("13322025 minutes.pdf") is None  # month 13, day 32
    assert M.parse_meeting_date("19990101 minutes.pdf") is None  # year out of range


def test_normalize_iso_handles_many_shapes():
    assert M.normalize_iso("2025-01-02") == "2025-01-02"
    assert M.normalize_iso("2025-01-02T09:30:00") == "2025-01-02"
    assert M.normalize_iso("1/2/2025") == "2025-01-02"
    assert M.normalize_iso("January 2, 2025") == "2025-01-02"
    assert M.normalize_iso("01022025") == "2025-01-02"
    assert M.normalize_iso("2025-13-40") is None  # invalid month/day
    assert M.normalize_iso("null") is None
    assert M.normalize_iso(None) is None
    assert M.normalize_iso("") is None


def test_normalize_body_routes_ids_names_and_labels():
    assert M.normalize_body(1) == "council"
    assert M.normalize_body("1") == "council"
    assert M.normalize_body("Village Council") == "council"
    assert M.normalize_body(2) == "pzdb"
    assert M.normalize_body("Planning Zoning & Design Board") == "pzdb"
    assert M.normalize_body("PZDB") == "pzdb"
    assert M.normalize_body("") is None
    assert M.normalize_body(None) is None


# --------------------------------------------------------------------------- #
# extract_links / discover_meetings
# --------------------------------------------------------------------------- #
def test_extract_links_filters_and_dedupes():
    html = f"""
      <a href="{BASE}01032024%20minutes.pdf">A</a>
      <a href="{BASE}01032024%20minutes.pdf">dup</a>
      <a href="{BASE}02072024%20minutes.pdf">B</a>
      <a href="https://estero-fl.gov/wp-content/uploads/other/file.pdf">ignored</a>
    """
    links = M.extract_links(html)
    assert links == [
        f"{BASE}01032024%20minutes.pdf",
        f"{BASE}02072024%20minutes.pdf",
    ]


def test_discover_meetings_from_minutes_links():
    html = (
        f'<a href="{BASE}01032024%20minutes.pdf"></a>'
        f'<a href="{BASE}02072024%20PZDB%20Minutes.pdf"></a>'
        f'<a href="{BASE}Cancellation%20Notice.pdf"></a>'
    )
    candidates, skipped = M.discover_meetings(html, "council")
    dates = [c["meeting_date"] for c in candidates]
    assert dates == ["2024-01-03", "2024-02-07"]
    assert all(c["body"] == "council" for c in candidates)
    assert skipped == ["Cancellation Notice.pdf"]


def test_discover_meetings_anchor_text_fallback():
    # No links match LINK_RE, so dates must be read from anchor *text*.
    html = (
        '<a href="https://estero-fl.gov/agendas/?m=1">January 13, 2026 PZDB Agenda</a>'
        '<a href="https://estero-fl.gov/agendas/?m=2">February 10, 2026 PZDB Agenda</a>'
    )
    candidates, _ = M.discover_meetings(html, "pzdb")
    dates = [c["meeting_date"] for c in candidates]
    assert dates == ["2026-01-13", "2026-02-10"]


# --------------------------------------------------------------------------- #
# diff_against_bronze
# --------------------------------------------------------------------------- #
def test_diff_against_bronze_returns_only_new():
    discovered = [
        {"body": "council", "meeting_date": "2024-01-03"},
        {"body": "council", "meeting_date": "2024-02-07"},  # new
        {"body": "pzdb", "meeting_date": "2024-03-11"},     # new
    ]
    bronze = [
        {"type_id": "1", "meeting_date": "2024-01-03"},
        {"type_name": "Planning Zoning & Design Board", "meeting_date": "2024-01-09"},
    ]
    new = M.diff_against_bronze(discovered, bronze)
    keys = {(c["body"], c["meeting_date"]) for c in new}
    assert keys == {("council", "2024-02-07"), ("pzdb", "2024-03-11")}


def test_diff_against_bronze_matches_across_date_shapes():
    # Bronze stores a datetime string; discovered is plain ISO -> still a match.
    discovered = [{"body": "council", "meeting_date": "2024-01-03"}]
    bronze = [{"type_id": "1", "meeting_date": "2024-01-03T09:30:00"}]
    assert M.diff_against_bronze(discovered, bronze) == []


def test_diff_against_bronze_dedupes_discovered():
    discovered = [
        {"body": "council", "meeting_date": "2024-05-01"},
        {"body": "council", "meeting_date": "2024-05-01"},  # duplicate
    ]
    new = M.diff_against_bronze(discovered, bronze_rows=[])
    assert len(new) == 1


def test_diff_against_bronze_drops_unparseable_rows():
    discovered = [
        {"body": "council", "meeting_date": "not-a-date"},
        {"body": "mystery-body", "meeting_date": "2024-05-01"},
    ]
    assert M.diff_against_bronze(discovered, bronze_rows=[]) == []


# --------------------------------------------------------------------------- #
# collect_candidate_meetings (network monkeypatched, bronze faked on disk)
# --------------------------------------------------------------------------- #
def _write_csv(path, header, rows):
    lines = [",".join(header)] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_collect_candidate_meetings_writes_only_new(tmp_path, monkeypatch):
    meetings_csv = tmp_path / "meetings.csv"
    documents_csv = tmp_path / "documents.csv"
    _write_csv(
        meetings_csv,
        ["meeting_id", "type_id", "meeting_date"],
        [["1", "1", "2024-01-03"]],  # council already known
    )
    _write_csv(
        documents_csv,
        ["document_id", "meeting_date", "type_name"],
        [["1", "2024-02-07", "Planning Zoning & Design Board"]],  # pzdb known
    )
    monkeypatch.setattr(M.config, "BRONZE_MEETINGS", meetings_csv)
    monkeypatch.setattr(M.config, "BRONZE_DOCUMENTS", documents_csv)

    pages = {
        "council": (
            f'<a href="{BASE}01032024%20minutes.pdf"></a>'   # known -> skip
            f'<a href="{BASE}03062024%20minutes.pdf"></a>'   # NEW
        ),
        "pzdb": (
            f'<a href="{BASE}02072024%20PZDB%20Minutes.pdf"></a>'  # known -> skip
            f'<a href="{BASE}04102024%20PZDB%20Minutes.pdf"></a>'  # NEW
        ),
    }
    monkeypatch.setattr(M, "SOURCES", {
        "council": "https://example/council",
        "pzdb": "https://example/pzdb",
    })
    monkeypatch.setattr(M, "fetch", lambda url: pages["pzdb" if "pzdb" in url else "council"])

    out = tmp_path / "extract" / "candidate_meetings.csv"
    report = M.collect_candidate_meetings(out_path=out)

    assert report["total_new"] == 2
    assert report["total_discovered"] == 4
    assert out.exists()

    import csv
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pairs = {(r["body"], r["meeting_date"]) for r in rows}
    assert pairs == {("council", "2024-03-06"), ("pzdb", "2024-04-10")}
    # type_id is populated for downstream review
    assert {r["type_id"] for r in rows} == {"1", "2"}


def test_collect_candidate_meetings_survives_fetch_errors(tmp_path, monkeypatch):
    _write_csv(tmp_path / "m.csv", ["type_id", "meeting_date"], [])
    _write_csv(tmp_path / "d.csv", ["type_name", "meeting_date"], [])
    monkeypatch.setattr(M.config, "BRONZE_MEETINGS", tmp_path / "m.csv")
    monkeypatch.setattr(M.config, "BRONZE_DOCUMENTS", tmp_path / "d.csv")

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(M, "fetch", boom)
    out = tmp_path / "extract" / "candidate_meetings.csv"
    report = M.collect_candidate_meetings(out_path=out)

    assert report["total_new"] == 0
    assert set(report["errors"]) == set(M.SOURCES)
    assert out.exists()  # header-only file still written
