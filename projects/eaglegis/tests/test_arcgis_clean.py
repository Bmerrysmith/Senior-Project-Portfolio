"""Tests for ArcGIS-based gold cleaning."""
from __future__ import annotations

from app.pipeline.publish.arcgis_clean import (
    board_for_meeting_type,
    clean_meetings_public_rows,
    pick_best_arcgis_location,
)


def test_board_for_meeting_type_maps_pzdb_and_council():
    assert board_for_meeting_type("PZDB Meeting") == "Planning Zoning & Design Board"
    assert board_for_meeting_type("Regular Council Meeting") == "Village Council"


def test_pick_best_arcgis_location_prefers_highest_confidence():
    items = [
        {"Location": "Low conf", "Latitude": "26.1", "Longitude": "-81.1", "GeocodeConfidence": "0.5"},
        {"Location": "High conf", "Latitude": "26.2", "Longitude": "-81.2", "GeocodeConfidence": "1.0"},
    ]
    best = pick_best_arcgis_location(items)
    assert best["Location"] == "High conf"


def test_clean_meetings_public_rows_overlays_arcgis_location():
    meetings = [{
        "ProjectName": "Test",
        "MeetingType": "Regular Council Meeting",
        "MeetingDate": "2020-01-08",
        "MeetingYear": "2020",
        "Status": "Accepted",
        "ActionTaken": "",
        "StartTime": "",
        "StaffCode": "",
        "Title": "Council",
        "MinutesURL": "",
        "DocDate": "",
        "LocationName": "Village of Estero Council Chambers",
        "Latitude": "26.4361",
        "Longitude": "-81.8157",
    }]
    arcgis = [{
        "Board": "Village Council",
        "MeetingDate": "2020-01-08",
        "Location": "20170 South Tamiami Trail, Estero, FL",
        "LocationName": "20170 South Tamiami Trail",
        "Latitude": "26.446015833153",
        "Longitude": "-81.815692187201",
        "GeocodeConfidence": "1.0",
        "ActionTaken": "Approved settlement agreement",
        "Outcome": "Approved settlement agreement",
        "Summary": "Settlement item",
        "Document_Link": "https://example.com/minutes.pdf",
    }]
    cleaned, stats = clean_meetings_public_rows(meetings, arcgis)
    assert stats["locations_updated"] == 1
    assert "Tamiami Trail" in cleaned[0]["LocationName"]
    assert cleaned[0]["Latitude"] == "26.446015833153"
    assert "Approved settlement agreement" in cleaned[0]["ActionTaken"]
