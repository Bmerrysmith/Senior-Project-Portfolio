"""
Data store served to the API.

Layered data sources, in order of preference:

  1. ``app/data/silver/*.csv`` — refined output of the pipeline
     (run with ``python -m app.pipeline.run``).
  2. ``app/data/meetings.csv`` / ``documents.csv`` (bronze) — used as a
     fallback when silver hasn't been built yet, with on-the-fly text
     cleaning so the API never serves the raw OCR-mangled text.

Reference data (projects, meeting types, locations, geometries) is loaded
from ``app/data/reference/*.yaml`` so non-developers can edit it.

Public API (the methods consumed by routers and services) is unchanged from
the previous implementation, so no router changes are required.
"""
from __future__ import annotations

import csv
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Optional

from app.pipeline import config as pipe_config
from app.pipeline import reference
from app.pipeline.clean.text import clean_action_text

_DATA_DIR = Path(__file__).parent

_NULL_TOKENS = {"", "null", "NULL", "None"}


def _null(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    return None if v in _NULL_TOKENS else v


def _parse_date(value: Optional[str]) -> Optional[date]:
    v = _null(value)
    if v is None:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    v = _null(value)
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _meetings_path() -> Path:
    return pipe_config.SILVER_MEETINGS if pipe_config.SILVER_MEETINGS.exists() else pipe_config.BRONZE_MEETINGS


def _documents_path() -> Path:
    return pipe_config.SILVER_DOCUMENTS if pipe_config.SILVER_DOCUMENTS.exists() else pipe_config.BRONZE_DOCUMENTS


def _is_future_placeholder(link_status: Optional[str]) -> bool:
    return (link_status or "").strip().lower() == pipe_config.FUTURE_PLACEHOLDER_TAG.lower()


def _load_meetings() -> list[dict]:
    path = _meetings_path()
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "meeting_id":               _parse_int(row.get("meeting_id")),
                "project_id":               _parse_int(row.get("project_id")),
                "type_id":                  _parse_int(row.get("type_id")),
                "meeting_date":             _parse_date(row.get("meeting_date")),
                "meeting_year":             _parse_int(row.get("meeting_year")),
                "location":                 _null(row.get("location", "")),
                "start_time":               _null(row.get("start_time", "")),
                "end_time":                 _null(row.get("end_time", "")),
                "action_taken":             clean_action_text(_null(row.get("action_taken", ""))),
                "status":                   _null(row.get("status", "")) or "Accepted",
                "approved_by_council_date": _parse_date(row.get("approved_by_council_date", "")),
                "doc_ref_code":             _null(row.get("doc_ref_code", "")),
                "filename":                 _null(row.get("filename", "")),
                "notes":                    clean_action_text(_null(row.get("notes", ""))),
                "location_id":              _parse_int(row.get("location_id", "")),
            })
    return rows


def _parse_float(value: Optional[str]) -> Optional[float]:
    v = _null(value)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _load_meeting_actions() -> list[dict]:
    """Load silver meeting_actions.csv.

    Gracefully returns ``[]`` when the file hasn't been built yet (the pipeline
    may not have run) — never raises, so the API stays up.
    """
    path = pipe_config.SILVER_MEETING_ACTIONS
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append({
                    "action_id":      _parse_int(row.get("action_id")),
                    "meeting_id":     _parse_int(row.get("meeting_id")),
                    "sequence":       _parse_int(row.get("sequence")),
                    "kind":           _null(row.get("kind", "")) or "Other",
                    "reference_code": _null(row.get("reference_code", "")),
                    "amount_usd":     _parse_float(row.get("amount_usd", "")),
                    "raw_text":       _null(row.get("raw_text", "")) or "",
                })
    except OSError:
        return []
    return rows


def _load_documents(include_planned: bool = False) -> list[dict]:
    path = _documents_path()
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            link_status = _null(row.get("link_status", ""))
            if not include_planned and _is_future_placeholder(link_status):
                continue
            rows.append({
                "document_id":   _parse_int(row.get("document_id")),
                "meeting_id":    _parse_int(row.get("meeting_id")),
                "title":         _null(row.get("title", "")) or "Untitled",
                "document_type": None,
                "file_name":     None,
                "file_url":      _null(row.get("file_url", "")),
                "upload_date":   _parse_date(row.get("doc_date", "")),
                "notes":         None,
                "doc_date":      _parse_date(row.get("doc_date", "")),
                "link_status":   link_status,
            })
    return rows


class CSVStore:
    """
    Read-only data access used by FastAPI routers and the GeoJSON service.

    Reference data is loaded once from YAML; row data is loaded once at
    construction time from silver (preferred) or bronze (fallback).
    """

    def __init__(self, *, include_planned_documents: bool = False) -> None:
        self._projects = reference.projects()
        self._meeting_types = reference.meeting_types()
        self._locations = reference.locations()
        geom = reference.geometries()
        self._road_geometries = geom["road_geometries"]
        self._area_geometries = geom["area_geometries"]
        self._meetings = _load_meetings()
        self._documents = _load_documents(include_planned=include_planned_documents)
        self._meeting_actions = _load_meeting_actions()

    def get_projects(self, status: Optional[str] = None) -> list[dict]:
        rows = deepcopy(self._projects)
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows

    def get_project(self, project_id: int) -> Optional[dict]:
        return next(
            (deepcopy(r) for r in self._projects if r["project_id"] == project_id),
            None,
        )

    def get_meeting_types(self) -> list[dict]:
        return deepcopy(self._meeting_types)

    def get_meeting_type(self, type_id: int) -> Optional[dict]:
        return next(
            (deepcopy(r) for r in self._meeting_types if r["type_id"] == type_id),
            None,
        )

    def get_meetings(
        self,
        project_id: Optional[int] = None,
        year: Optional[int] = None,
        status: Optional[str] = None,
        type_id: Optional[int] = None,
        location_id: Optional[int] = None,
    ) -> list[dict]:
        rows = deepcopy(self._meetings)
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        if year is not None:
            rows = [r for r in rows if r["meeting_year"] == year]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if type_id is not None:
            rows = [r for r in rows if r["type_id"] == type_id]
        if location_id is not None:
            rows = [r for r in rows if r.get("location_id") == location_id]
        return rows

    def get_meeting(self, meeting_id: int) -> Optional[dict]:
        return next(
            (deepcopy(r) for r in self._meetings if r["meeting_id"] == meeting_id),
            None,
        )

    def get_locations(
        self,
        project_id: Optional[int] = None,
        location_type: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(self._locations)
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        if location_type:
            rows = [r for r in rows if r["location_type"] == location_type]
        return rows

    def get_location(self, location_id: int) -> Optional[dict]:
        return next(
            (deepcopy(r) for r in self._locations if r["location_id"] == location_id),
            None,
        )

    def get_documents(
        self,
        meeting_id: Optional[int] = None,
        document_type: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(self._documents)
        if meeting_id is not None:
            rows = [r for r in rows if r["meeting_id"] == meeting_id]
        if document_type:
            rows = [r for r in rows if r["document_type"] == document_type]
        return rows

    def get_document(self, document_id: int) -> Optional[dict]:
        return next(
            (deepcopy(r) for r in self._documents if r["document_id"] == document_id),
            None,
        )

    def get_actions(
        self,
        meeting_id: Optional[int] = None,
        kind: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(self._meeting_actions)
        if meeting_id is not None:
            rows = [r for r in rows if r["meeting_id"] == meeting_id]
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        return rows

    def get_action(self, action_id: int) -> Optional[dict]:
        return next(
            (deepcopy(r) for r in self._meeting_actions if r["action_id"] == action_id),
            None,
        )

    def get_road_geometry(self, location_id: int) -> Optional[list[list[float]]]:
        return self._road_geometries.get(location_id)

    def get_area_geometry(self, location_id: int) -> Optional[list[list[list[float]]]]:
        return self._area_geometries.get(location_id)
