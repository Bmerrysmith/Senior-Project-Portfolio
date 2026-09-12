"""
Reference data loader.

Reads YAML files in app/data/reference/ and exposes them as plain dicts/lists.
A small in-memory cache avoids re-reading files on every call. Call
``reload()`` after editing a YAML file in tests or notebooks.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.pipeline import config
from app.pipeline.validate.schemas import LocationRow, validate_rows


def _read_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def projects() -> list[dict]:
    return list(_read_yaml(config.REF_PROJECTS) or [])


@lru_cache(maxsize=1)
def meeting_types() -> list[dict]:
    return list(_read_yaml(config.REF_MEETING_TYPES) or [])


@lru_cache(maxsize=1)
def locations() -> list[dict]:
    raw = list(_read_yaml(config.REF_LOCATIONS) or [])
    valid, rejects = validate_rows(raw, LocationRow)
    if rejects:
        preview = rejects[:3]
        raise ValueError(
            f"Invalid reference locations in {config.REF_LOCATIONS}: {preview}"
        )

    project_fk_errors = [
        f"location_id={loc.location_id} references unknown project_id={loc.project_id}"
        for loc in valid
        if loc.project_id not in project_ids()
    ]
    if project_fk_errors:
        raise ValueError(
            f"Invalid reference locations project_id values: {project_fk_errors[:3]}"
        )

    return [loc.model_dump() for loc in valid]


@lru_cache(maxsize=1)
def geometries() -> dict:
    raw = _read_yaml(config.REF_GEOMETRIES) or {}
    return {
        "road_geometries": {int(k): v for k, v in (raw.get("road_geometries") or {}).items()},
        "area_geometries": {int(k): v for k, v in (raw.get("area_geometries") or {}).items()},
    }


def project_ids() -> set[int]:
    return {p["project_id"] for p in projects()}


def meeting_type_ids() -> set[int]:
    return {t["type_id"] for t in meeting_types()}


def location_ids() -> set[int]:
    return {loc["location_id"] for loc in locations()}


def reload() -> None:
    """Drop cached reference data; the next access re-reads from disk."""
    projects.cache_clear()
    meeting_types.cache_clear()
    locations.cache_clear()
    geometries.cache_clear()
