"""
Publish merged ArcGIS agenda-item CSV to app/data/gold/.

This is the canonical public deliverable for map + ML use. Rows come from
normalized_csv_council and normalized_csv_pilot arcgis_agenda_map_data.csv,
with LandUseCategory added when missing.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from app.pipeline import config
from app.pipeline.classify.land_use import LAND_USE_CATEGORIES, classify_land_use
from app.pipeline.load.silver import _read_csv
from app.pipeline.publish.ai_gold import _atomic_write_csv, _rel

ARCGIS_GOLD_FIELDS = [
    "ProjectName",
    "Board",
    "MeetingFormat",
    "MeetingType",
    "MeetingDate",
    "ArcGIS_Date",
    "MeetingYear",
    "Status",
    "AgendaItemID",
    "AgendaItemNumber",
    "AgendaItemType",
    "LandUseCategory",
    "ProjectTitle",
    "Summary",
    "ActionTaken",
    "Outcome",
    "MotionText",
    "ProposedBy",
    "SecondedBy",
    "VoteResult",
    "ApplicantName",
    "ApplicationID",
    "District",
    "LocationName",
    "Location",
    "Latitude",
    "Longitude",
    "GeocodeConfidence",
    "StaffCode",
    "Filename",
    "Document_Link",
    "RecordType",
]


def _source_paths() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    council = config.NORMALIZED_COUNCIL_DIR / "arcgis_agenda_map_data.csv"
    if council.exists():
        out.append(("council", council))
    pzdb = config.NORMALIZED_PZDB_DIR / "arcgis_agenda_map_data.csv"
    if pzdb.exists():
        out.append(("pzdb", pzdb))
    return out


def _board_slug(board: str) -> str:
    board = (board or "").strip()
    if "Planning" in board:
        return "pzdb"
    if "Council" in board:
        return "council"
    return board.lower().replace(" ", "_") or "other"


def _normalize_row(raw: dict[str, Any], *, source_tag: str) -> tuple[dict[str, str], str]:
    row: dict[str, str] = {}
    for field in ARCGIS_GOLD_FIELDS:
        if field == "LandUseCategory":
            existing = str(raw.get("LandUseCategory") or "").strip()
            row[field] = existing or classify_land_use(raw)
        else:
            row[field] = str(raw.get(field) or "")

    agenda_id = row.get("AgendaItemID") or ""
    board = row.get("Board") or source_tag
    record_key = f"{_board_slug(board)}:{agenda_id}" if agenda_id else ""
    return row, record_key


def build_arcgis_gold() -> dict[str, Any]:
    """Merge council + PZDB arcgis rows into app/data/gold/arcgis_agenda_map_data.csv."""
    sources = _source_paths()
    if not sources:
        _atomic_write_csv(config.GOLD_ARCGIS_PUBLIC, ARCGIS_GOLD_FIELDS, [])
        return {
            "rows": 0,
            "categories": {},
            "sources": [],
            "path": _rel(config.GOLD_ARCGIS_PUBLIC),
            "skipped": "no arcgis_agenda_map_data.csv inputs found",
        }

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    source_report: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {cat: 0 for cat in LAND_USE_CATEGORIES}

    for source_tag, path in sources:
        raw_rows = _read_csv(path)
        added = 0
        for raw in raw_rows:
            if str(raw.get("RecordType") or "").strip() not in ("", "AgendaItemLocation"):
                continue
            normalized, key = _normalize_row(raw, source_tag=source_tag)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            category_counts[normalized["LandUseCategory"]] = (
                category_counts.get(normalized["LandUseCategory"], 0) + 1
            )
            rows.append(normalized)
            added += 1
        source_report.append({
            "tag": source_tag,
            "path": _rel(path),
            "input_rows": len(raw_rows),
            "output_rows": added,
        })

    rows.sort(
        key=lambda r: (r.get("MeetingDate") or "", r.get("Board") or "", r.get("AgendaItemID") or ""),
        reverse=True,
    )
    _atomic_write_csv(config.GOLD_ARCGIS_PUBLIC, ARCGIS_GOLD_FIELDS, rows)

    return {
        "rows": len(rows),
        "categories": {k: v for k, v in category_counts.items() if v},
        "sources": source_report,
        "path": _rel(config.GOLD_ARCGIS_PUBLIC),
    }
