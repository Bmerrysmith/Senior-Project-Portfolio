from __future__ import annotations

from app.pipeline.validate import pdf_location


def test_pdf_location_verification_matches_expected_location(monkeypatch):
    meetings = [{
        "meeting_id": "1",
        "type_id": "1",
        "meeting_date": "2024-01-03",
        "location": "Village of Estero Council Chambers",
        "location_id": "6",
    }]
    documents = [{
        "meeting_id": "1",
        "file_url": "https://example.test/minutes.pdf",
        "link_status": "Uploaded",
    }]

    def fake_read_csv(path):
        if "meetings.csv" in str(path):
            return meetings
        return documents

    monkeypatch.setattr(pdf_location, "_read_csv", fake_read_csv)
    monkeypatch.setattr(
        pdf_location.reference,
        "locations",
        lambda: [{
            "location_id": 6,
            "location_name": "Village of Estero Council Chambers",
            "address": "9401 Corkscrew Palms Blvd, Estero FL 33928",
        }],
    )
    monkeypatch.setattr(pdf_location.reference, "meeting_types", lambda: [{"type_id": 1, "type_name": "Village Council"}])
    monkeypatch.setattr(pdf_location, "load_minutes_index", lambda: {"_meta": {}})

    report = pdf_location.verify_locations_from_minutes_pdfs(
        pdf_fetcher=lambda url: b"%PDF-test%",
        text_extractor=lambda payload: "Meeting held at Village of Estero Council Chambers.",
    )
    assert report["checked"] == 1
    assert report["matched"] == 1
    assert report["mismatched"] == 0
    assert not report["strict_violations"]


def test_pdf_location_verification_strict_on_mismatch(monkeypatch):
    meetings = [{
        "meeting_id": "2",
        "type_id": "2",
        "meeting_date": "2024-02-14",
        "location": "Village of Estero Council Chambers",
        "location_id": "6",
    }]
    documents = [{
        "meeting_id": "2",
        "file_url": "https://example.test/minutes2.pdf",
        "link_status": "Uploaded",
    }]

    def fake_read_csv(path):
        if "meetings.csv" in str(path):
            return meetings
        return documents

    monkeypatch.setattr(pdf_location, "_read_csv", fake_read_csv)
    monkeypatch.setattr(
        pdf_location.reference,
        "locations",
        lambda: [{
            "location_id": 6,
            "location_name": "Village of Estero Council Chambers",
            "address": "9401 Corkscrew Palms Blvd, Estero FL 33928",
        }],
    )
    monkeypatch.setattr(pdf_location.reference, "meeting_types", lambda: [{"type_id": 2, "type_name": "Planning Zoning & Design Board"}])
    monkeypatch.setattr(pdf_location, "load_minutes_index", lambda: {"_meta": {}})

    report = pdf_location.verify_locations_from_minutes_pdfs(
        pdf_fetcher=lambda url: b"%PDF-test%",
        text_extractor=lambda payload: "Meeting held at Another Community Center.",
    )
    assert report["checked"] == 1
    assert report["matched"] == 0
    assert report["mismatched"] == 1
    assert report["strict_violations"]


def test_pdf_location_fetch_failure_is_warning_not_strict(monkeypatch):
    """A PDF we can't fetch (e.g. CI runner blocked by a WAF) must be a
    non-fatal warning, never a strict violation that fails the build."""
    meetings = [{
        "meeting_id": "3",
        "type_id": "2",
        "meeting_date": "2024-03-13",
        "location": "Village of Estero Council Chambers",
        "location_id": "6",
    }]
    documents = [{
        "meeting_id": "3",
        "file_url": "https://example.test/minutes3.pdf",
        "link_status": "Uploaded",
    }]

    def fake_read_csv(path):
        if "meetings.csv" in str(path):
            return meetings
        return documents

    monkeypatch.setattr(pdf_location, "_read_csv", fake_read_csv)
    monkeypatch.setattr(
        pdf_location.reference,
        "locations",
        lambda: [{
            "location_id": 6,
            "location_name": "Village of Estero Council Chambers",
            "address": "9401 Corkscrew Palms Blvd, Estero FL 33928",
        }],
    )
    monkeypatch.setattr(pdf_location.reference, "meeting_types", lambda: [{"type_id": 2, "type_name": "Planning Zoning & Design Board"}])
    monkeypatch.setattr(pdf_location, "load_minutes_index", lambda: {"_meta": {}})

    def blocked_fetcher(url):
        raise OSError("HTTP 403: blocked by WAF / datacenter IP")

    report = pdf_location.verify_locations_from_minutes_pdfs(
        pdf_fetcher=blocked_fetcher,
        text_extractor=lambda payload: "unused",
    )
    assert report["checked"] == 1
    assert report["pdf_fetch_errors"] == 1
    assert report["fetch_warnings"]
    assert not report["strict_violations"]
