"""
Smoke tests for the CSV/silver-backed read-API and GeoJSON GIS layers.

These build a fresh ``FastAPI()`` app that includes ONLY the six read
routers, deliberately avoiding ``app.main`` so the Supabase/db import path
is never touched. The tests are credential-free and fast.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import pin_comments_store
from app.routers import (
    documents,
    layers,
    locations,
    meeting_types,
    meetings,
    projects,
)


def _client() -> TestClient:
    app = FastAPI()
    for module in (meetings, projects, documents, meeting_types, locations, layers):
        app.include_router(module.router)
    return TestClient(app)


def test_list_endpoints_return_nonempty_lists():
    client = _client()
    for path in ("/meetings/", "/projects/", "/documents/", "/meeting-types/", "/locations/"):
        res = client.get(path)
        assert res.status_code == 200, f"{path} -> {res.status_code}"
        body = res.json()
        assert isinstance(body, list)
        assert len(body) > 0, f"{path} returned an empty list"


def test_project_detail_has_enriched_fields():
    client = _client()
    first = client.get("/projects/").json()[0]
    res = client.get(f"/projects/{first['project_id']}")
    assert res.status_code == 200
    detail = res.json()
    assert "meeting_count" in detail
    assert "location_count" in detail
    assert detail["project_id"] == first["project_id"]


def test_meeting_detail_has_documents_and_context():
    client = _client()
    first = client.get("/meetings/").json()[0]
    res = client.get(f"/meetings/{first['meeting_id']}")
    assert res.status_code == 200
    detail = res.json()
    assert "project_name" in detail
    assert "meeting_type_name" in detail
    assert "documents" in detail
    assert isinstance(detail["documents"], list)


def test_points_layer_is_geojson_with_features():
    client = _client()
    res = client.get("/layers/points")
    assert res.status_code == 200
    fc = res.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    props = fc["features"][0]["properties"]
    for key in ("project_name", "project_status", "meeting_count"):
        assert key in props


def test_roads_layer_has_at_least_two_linestrings():
    client = _client()
    res = client.get("/layers/roads")
    assert res.status_code == 200
    fc = res.json()
    assert fc["type"] == "FeatureCollection"
    line_features = [f for f in fc["features"] if f["geometry"]["type"] == "LineString"]
    assert len(line_features) >= 2


def test_admin_pin_comments_require_key(tmp_path, monkeypatch):
    comments_path = tmp_path / "pin_comments.json"
    comments_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pin_comments_store, "_PIN_COMMENTS_PATH", comments_path)
    monkeypatch.setattr(locations.settings, "admin_key", "test-admin-key")

    client = _client()
    assert client.get("/locations/admin/verify").status_code == 401

    headers = {"X-Admin-Key": "test-admin-key"}
    assert client.get("/locations/admin/verify", headers=headers).json() == {"ok": True}

    res = client.put(
        "/locations/admin/pin-comments/2",
        headers=headers,
        json={"text": "Check geocode", "updated_by": "admin"},
    )
    assert res.status_code == 200
    assert res.json()["text"] == "Check geocode"
    assert client.get("/locations/admin/pin-comments", headers=headers).json()["2"]["text"] == "Check geocode"
