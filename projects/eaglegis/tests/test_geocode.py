"""
Tests for the Census-geocoder enrichment stage
(``app/pipeline/enrich/geocode.py``).

NO real network is used: the cache-hit path asserts the fetcher is never
called, and ``run_geocode`` is exercised with a fetcher that raises if invoked
(today every reference location already has coordinates, so it must be a
no-op).
"""
from __future__ import annotations

from app.pipeline import reference
from app.pipeline.enrich.geocode import (
    _parse_coordinates,
    geocode_address,
    run_geocode,
)


def _boom_fetcher(url: str) -> dict:
    raise AssertionError(f"network fetch must not happen (url={url})")


def test_parse_coordinates_from_census_payload():
    payload = {
        "result": {
            "addressMatches": [
                {"coordinates": {"x": -81.8062, "y": 26.4361}},
            ]
        }
    }
    assert _parse_coordinates(payload) == (26.4361, -81.8062)


def test_parse_coordinates_empty_matches():
    assert _parse_coordinates({"result": {"addressMatches": []}}) is None
    assert _parse_coordinates({}) is None


def test_geocode_address_cache_hit_no_network():
    cache = {"9401 Corkscrew Palms Blvd, Estero FL": {"latitude": 26.4361, "longitude": -81.8062}}
    lat, lon = geocode_address("9401 Corkscrew Palms Blvd, Estero FL", cache, fetcher=_boom_fetcher)
    assert (lat, lon) == (26.4361, -81.8062)


def test_geocode_address_cache_miss_uses_fetcher_then_caches():
    cache: dict = {}
    calls: list[str] = []

    def fake_fetcher(url: str) -> dict:
        calls.append(url)
        return {"result": {"addressMatches": [{"coordinates": {"x": -81.80, "y": 26.43}}]}}

    coords = geocode_address("123 Main St, Estero FL", cache, fetcher=fake_fetcher)
    assert coords == (26.43, -81.80)
    assert len(calls) == 1
    # Second call is served from cache (fetcher would blow up).
    again = geocode_address("123 Main St, Estero FL", cache, fetcher=_boom_fetcher)
    assert again == (26.43, -81.80)


def test_geocode_address_force_refresh_bypasses_cache():
    cache = {"123 Main St, Estero FL": {"latitude": 26.1, "longitude": -81.1}}
    calls: list[str] = []

    def fake_fetcher(url: str) -> dict:
        calls.append(url)
        return {"result": {"addressMatches": [{"coordinates": {"x": -81.80, "y": 26.43}}]}}

    refreshed = geocode_address(
        "123 Main St, Estero FL",
        cache,
        fetcher=fake_fetcher,
        force_refresh=True,
    )
    assert refreshed == (26.43, -81.80)
    assert len(calls) == 1


def test_run_geocode_is_noop_when_all_locations_have_coords():
    # Sanity: the seeded reference data has coordinates for every location.
    assert all(
        loc.get("latitude") is not None and loc.get("longitude") is not None
        for loc in reference.locations()
    )

    report = run_geocode(
        fetcher=_boom_fetcher,
        cache={},
        write_cache=False,
        write_locations=False,
    )
    assert report["missing"] == 0
    assert report["filled"] == 0
    assert report["checked"] == len(reference.locations())


def test_run_geocode_reports_live_drift_when_verifying_existing():
    def fake_fetcher(url: str) -> dict:
        return {"result": {"addressMatches": [{"coordinates": {"x": -82.50, "y": 28.50}}]}}

    report = run_geocode(
        fetcher=fake_fetcher,
        cache={},
        write_cache=False,
        write_locations=False,
        verify_existing=True,
        force_refresh=True,
        mismatch_threshold_meters=10.0,
    )
    assert report["verified"] >= 1
    assert report["mismatch_over_threshold"] >= 1
