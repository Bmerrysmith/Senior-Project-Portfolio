"""
Geocoding enrichment using the FREE U.S. Census Geocoder.

Fills missing latitude/longitude for reference locations that lack
coordinates. Uses only the stdlib (``urllib``) — no new dependencies — and
caches every lookup in ``app/data/reference/geocode_cache.json`` so repeated
runs (and tests) never re-hit the network.

Design for testability
-----------------------
All network access goes through an injectable ``fetcher(url) -> dict``. Tests
pass either a pre-seeded cache (cache-first => no fetch) or a fake fetcher, so
no real network call is ever made in CI.

The Census "onelineaddress" endpoint::

    https://geocoding.geo.census.gov/geocoder/locations/onelineaddress
        ?address=<urlencoded>&benchmark=Public_AR_Current&format=json

returns ``result.addressMatches[*].coordinates = {"x": <lon>, "y": <lat>}``.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import yaml

from app.pipeline import config, reference
from app.pipeline.validate.schemas import in_estero_bbox

CENSUS_ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
BENCHMARK = "Public_AR_Current"

Fetcher = Callable[[str], dict]


def _build_url(address: str) -> str:
    query = urllib.parse.urlencode({
        "address": address,
        "benchmark": BENCHMARK,
        "format": "json",
    })
    return f"{CENSUS_ONELINE_URL}?{query}"


def _default_fetcher(url: str) -> dict:
    """Real network fetch. Never called when a cache hit or fake fetcher is used."""
    req = urllib.request.Request(url, headers={"User-Agent": "EagleGIS-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 (trusted gov host)
        return json.load(resp)


def load_cache(path: Optional[Path] = None) -> dict:
    """Load the geocode cache, returning {} when the file is absent/corrupt."""
    path = path or config.GEOCODE_CACHE
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict, path: Optional[Path] = None) -> None:
    path = path or config.GEOCODE_CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


def _parse_coordinates(payload: dict) -> Optional[tuple[float, float]]:
    """Pull (latitude, longitude) out of a Census geocoder JSON response."""
    try:
        matches = payload["result"]["addressMatches"]
    except (KeyError, TypeError):
        return None
    if not matches:
        return None
    coords = matches[0].get("coordinates") or {}
    lon, lat = coords.get("x"), coords.get("y")
    if lon is None or lat is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def geocode_address(
    address: str,
    cache: dict,
    fetcher: Fetcher = _default_fetcher,
    force_refresh: bool = False,
) -> Optional[tuple[float, float]]:
    """Resolve ``address`` to ``(latitude, longitude)``, cache-first.

    On a cache hit the ``fetcher`` is never invoked. On a miss the fetcher is
    called, the (possibly ``None``) result is written back into ``cache`` keyed
    by the raw address string, and returned. Mutates ``cache`` in place.
    """
    key = (address or "").strip()
    if not key:
        return None
    if not force_refresh and key in cache:
        cached = cache[key]
        if not cached:
            return None
        return float(cached["latitude"]), float(cached["longitude"])

    payload = fetcher(_build_url(key))
    coords = _parse_coordinates(payload)
    if coords is None:
        cache[key] = None
        return None
    lat, lon = coords
    cache[key] = {"latitude": lat, "longitude": lon}
    return lat, lon


def _missing_coords(loc: dict) -> bool:
    return loc.get("latitude") in (None, "") or loc.get("longitude") in (None, "")


def _haversine_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius_m = 6_371_000
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def run_geocode(
    *,
    fetcher: Fetcher = _default_fetcher,
    cache: Optional[dict] = None,
    write_cache: bool = True,
    write_locations: bool = True,
    verify_existing: bool = False,
    mismatch_threshold_meters: float = config.GEOCODE_MISMATCH_THRESHOLD_METERS,
    force_refresh: bool = False,
) -> dict:
    """Fill missing lat/long on reference locations via the geocoder.

    Returns a report dict. Today all locations already carry coordinates, so
    this is a no-op (``filled == 0``); the stage exists to future-proof newly
    added locations. Network access is fully injectable for offline testing.
    """
    cache = load_cache() if cache is None else cache
    locations = reference.locations()

    report = {
        "checked": len(locations),
        "missing": 0,
        "filled": 0,
        "unresolved": 0,
        "resolved": 0,
        "verified": 0,
        "mismatch_over_threshold": 0,
        "outside_bbox": 0,
        "strict_violations": [],
        "geocoded_location_ids": [],
    }
    updated: list[dict] = []
    changed = False

    for loc in locations:
        loc = dict(loc)
        if _missing_coords(loc):
            report["missing"] += 1
            address = loc.get("address") or loc.get("location_name") or ""
            coords = (
                geocode_address(
                    address,
                    cache,
                    fetcher=fetcher,
                    force_refresh=force_refresh,
                )
                if address else None
            )
            if coords:
                loc["latitude"], loc["longitude"] = coords
                report["filled"] += 1
                report["resolved"] += 1
                report["geocoded_location_ids"].append(int(loc["location_id"]))
                changed = True
                if not in_estero_bbox(float(loc["latitude"]), float(loc["longitude"])):
                    report["outside_bbox"] += 1
                    if len(report["strict_violations"]) < 25:
                        report["strict_violations"].append(
                            f"location_id={loc['location_id']} geocoded outside ESTERO_BBOX"
                        )
            else:
                report["unresolved"] += 1
                if len(report["strict_violations"]) < 25:
                    report["strict_violations"].append(
                        f"location_id={loc.get('location_id')} unresolved geocode"
                    )
        elif verify_existing:
            address = loc.get("address") or loc.get("location_name") or ""
            if address:
                coords = geocode_address(
                    address,
                    cache,
                    fetcher=fetcher,
                    force_refresh=force_refresh,
                )
                report["verified"] += 1
                if coords:
                    report["resolved"] += 1
                    lat, lon = coords
                    source_lat = float(loc["latitude"])
                    source_lon = float(loc["longitude"])
                    drift_m = _haversine_meters(source_lat, source_lon, lat, lon)
                    if drift_m > mismatch_threshold_meters:
                        report["mismatch_over_threshold"] += 1
                        if len(report["strict_violations"]) < 25:
                            report["strict_violations"].append(
                                f"location_id={loc['location_id']} geocode drift {drift_m:.1f}m exceeds {mismatch_threshold_meters:.1f}m"
                            )
                    if not in_estero_bbox(lat, lon):
                        report["outside_bbox"] += 1
                        if len(report["strict_violations"]) < 25:
                            report["strict_violations"].append(
                                f"location_id={loc['location_id']} live geocode outside ESTERO_BBOX"
                            )
        updated.append(loc)

    if write_cache:
        save_cache(cache)
    if write_locations and changed:
        with open(config.REF_LOCATIONS, "w", encoding="utf-8") as f:
            yaml.safe_dump(updated, f, sort_keys=False, allow_unicode=True)
        reference.reload()

    return report
