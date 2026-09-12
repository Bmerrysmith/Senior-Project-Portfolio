"""
Gold-layer publish step: denormalized public CSV for the GitHub Pages frontend.

Joins silver meetings + reference YAML + silver documents (+ optional
minutes_index.json) into the 14-column schema expected by index.html:

  ProjectName, MeetingType, MeetingDate, MeetingYear, Status, Finalized,
  InProgress, InProgressNote, ActionTaken, StartTime, StaffCode, Title,
  MinutesURL, DocDate, LocationName, Latitude, Longitude
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.pipeline import config, reference
from app.pipeline.collect.minutes import load_minutes_index, resolve_minutes_url
from app.pipeline.load.silver import _atomic_write_csv, _read_csv
from app.pipeline.extract.in_progress import gold_in_progress_columns
from app.pipeline.validate.schemas import in_estero_bbox
from app.pipeline.publish.ai_gold import build_ai_gold
from app.pipeline.publish.arcgis_clean import clean_meetings_public_rows
from app.pipeline.publish.arcgis_gold import build_arcgis_gold

SITE_MANIFEST_VERSION = 2

# Frontend filter chips / colors key off these display names (see index.html TYPES).
TYPE_DISPLAY_NAMES: dict[str, str] = {
    "Village Council": "Regular Council Meeting",
    "Planning Zoning & Design Board": "PZDB Meeting",
    "Public Hearing": "Public Hearing",
    "Workshop": "Council Workshop",
}

GOLD_FIELDS = [
    "ProjectName",
    "MeetingType",
    "MeetingDate",
    "MeetingYear",
    "Status",
    "Finalized",
    "InProgress",
    "InProgressNote",
    "ActionTaken",
    "StartTime",
    "StaffCode",
    "Title",
    "MinutesURL",
    "DocDate",
    "LocationName",
    "Latitude",
    "Longitude",
]

# Additive companion file: one row per structured meeting action. Kept SEPARATE
# from GOLD_FIELDS so the 14-column public meetings contract is never touched.
GOLD_ACTION_FIELDS = [
    "ActionId",
    "MeetingId",
    "MeetingDate",
    "ProjectName",
    "MeetingType",
    "Sequence",
    "Kind",
    "ReferenceCode",
    "AmountUSD",
    "RawText",
]


def _atomic_write_json_compact(path: Path, payload: Any) -> None:
    """Write compact JSON atomically (smaller deliverable for the static site)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"), default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": _rel(path), "exists": False}
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return {
        "path": _rel(path),
        "exists": True,
        "sha256": h.hexdigest(),
        "bytes": size,
    }


def _rel(path: Path) -> str:
    return path.relative_to(config.DATA_DIR.parent.parent).as_posix()


def _clear_year_shards() -> None:
    """Remove stale shard files when the dataset is below the shard threshold."""
    if not config.GOLD_SHARDS_DIR.exists():
        return
    for path in config.GOLD_SHARDS_DIR.glob("*.json"):
        path.unlink()
    try:
        config.GOLD_SHARDS_DIR.rmdir()
    except OSError:
        pass


def _write_year_shards(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Emit per-year JSON shards when the dataset exceeds GOLD_SHARD_THRESHOLD."""
    by_year: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_year[str(row.get("MeetingYear") or "unknown")].append(row)

    shards: list[dict[str, Any]] = []
    config.GOLD_SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    for year in sorted(by_year.keys(), reverse=True):
        year_rows = by_year[year]
        shard_path = config.GOLD_SHARDS_DIR / f"{year}.json"
        _atomic_write_json_compact(shard_path, year_rows)
        shards.append({
            "year": year,
            "rows": len(year_rows),
            "path": _rel(shard_path),
        })
    return shards


def _build_site_manifest(
    rows: list[dict[str, str]],
    *,
    shard_report: list[dict[str, Any]] | None,
    arcgis_report: dict[str, Any] | None = None,
    ai_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meetings_csv = _file_fingerprint(config.GOLD_MEETINGS_PUBLIC)
    meetings_json = _file_fingerprint(config.GOLD_MEETINGS_JSON)
    minutes = _file_fingerprint(config.MINUTES_INDEX)
    years = sorted({str(r["MeetingYear"]) for r in rows if r.get("MeetingYear")}, reverse=True)
    types = sorted({str(r["MeetingType"]) for r in rows if r.get("MeetingType")})
    delivery = "sharded" if shard_report else "monolith"

    manifest: dict[str, Any] = {
        "version": SITE_MANIFEST_VERSION,
        "primary": "arcgis",
        "delivery": delivery,
        "meetings": {
            "rows": len(rows),
            "years": years,
            "types": types,
            "csv": _rel(config.GOLD_MEETINGS_PUBLIC),
            "json": _rel(config.GOLD_MEETINGS_JSON),
            "sha256": meetings_json.get("sha256") or meetings_csv.get("sha256"),
            "bytes": meetings_json.get("bytes") or meetings_csv.get("bytes"),
            "shards": shard_report,
        },
        "minutes_index": minutes,
    }

    if arcgis_report is not None:
        arcgis_csv = _file_fingerprint(config.GOLD_ARCGIS_PUBLIC)
        manifest["arcgis"] = {
            "rows": arcgis_report.get("rows", 0),
            "categories": arcgis_report.get("categories", {}),
            "csv": _rel(config.GOLD_ARCGIS_PUBLIC),
            "sha256": arcgis_csv.get("sha256"),
            "bytes": arcgis_csv.get("bytes"),
            "sources": arcgis_report.get("sources", []),
        }

    if ai_report is not None:
        ai_csv = _file_fingerprint(config.GOLD_AI_PUBLIC)
        ai_jsonl = _file_fingerprint(config.GOLD_AI_JSONL)
        manifest["ai"] = {
            "rows": ai_report.get("rows", 0),
            "ai_ready": ai_report.get("ai_ready", 0),
            "review_required": ai_report.get("review_required", 0),
            "csv": _rel(config.GOLD_AI_PUBLIC),
            "jsonl": _rel(config.GOLD_AI_JSONL),
            "sha256": ai_jsonl.get("sha256") or ai_csv.get("sha256"),
            "bytes": ai_jsonl.get("bytes") or ai_csv.get("bytes"),
            "sources": ai_report.get("sources", []),
        }

    return manifest


def _index_by_id(rows: list[dict], key: str) -> dict[int, dict]:
    return {int(r[key]): r for r in rows if r.get(key) is not None}


def _locations_by_project(locations: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for loc in locations:
        pid = loc.get("project_id")
        if pid is None:
            continue
        out.setdefault(int(pid), []).append(loc)
    return out


def _resolve_location(
    meeting: dict,
    loc_by_id: dict[int, dict],
    locs_by_project: dict[int, list[dict]],
    geocoded_location_ids: set[int] | None = None,
) -> tuple[str, str, str, str]:
    """Return (location_name, latitude, longitude, confidence)."""
    geocoded_location_ids = geocoded_location_ids or set()
    lid = meeting.get("location_id")
    if lid not in (None, ""):
        lid_int = int(lid)
        loc = loc_by_id.get(lid_int)
        if loc:
            confidence = (
                "geocoded" if lid_int in geocoded_location_ids else "exact_location_id"
            )
            return (
                loc.get("location_name") or meeting.get("location") or "",
                _fmt_coord(loc.get("latitude")),
                _fmt_coord(loc.get("longitude")),
                confidence,
            )
    pid = meeting.get("project_id")
    if pid is not None:
        for loc in locs_by_project.get(int(pid), []):
            loc_id = loc.get("location_id")
            confidence = (
                "geocoded" if loc_id in geocoded_location_ids else "project_fallback"
            )
            return (
                loc.get("location_name") or meeting.get("location") or "",
                _fmt_coord(loc.get("latitude")),
                _fmt_coord(loc.get("longitude")),
                confidence,
            )
    if meeting.get("location"):
        return (meeting.get("location") or "", "", "", "text_only")
    return ("", "", "", "missing")


def _meeting_finalized(status: str, minutes_url: str) -> str:
    """Whether official minutes are posted (public-facing plain label).

    Returns ``Yes``, ``No``, or ``Cancelled``.
    """
    if (status or "").strip().lower() == "cancelled":
        return "Cancelled"
    if (minutes_url or "").strip().startswith("http"):
        return "Yes"
    return "No"


def _fmt_coord(val: Any) -> str:
    if val is None or val == "":
        return ""
    try:
        return str(float(val))
    except (TypeError, ValueError):
        return str(val)


def _documents_by_meeting(documents: list[dict]) -> dict[int, dict]:
    """Prefer documents with a confirmed upload over placeholders."""
    best: dict[int, dict] = {}
    for doc in documents:
        mid = doc.get("meeting_id")
        if mid is None:
            continue
        mid = int(mid)
        prev = best.get(mid)
        if prev is None:
            best[mid] = doc
            continue
        prev_ok = (prev.get("link_status") or "").lower() == "uploaded"
        cur_ok = (doc.get("link_status") or "").lower() == "uploaded"
        if cur_ok and not prev_ok:
            best[mid] = doc
    return best


def _meeting_type_display(type_name: str) -> str:
    return TYPE_DISPLAY_NAMES.get(type_name, type_name or "Other")


def _resolve_minutes_url_for_row(
    meeting: dict,
    type_name: str,
    doc: dict | None,
    minutes_index: dict[str, Any],
) -> str:
    if doc and doc.get("file_url"):
        return str(doc["file_url"]).strip()
    iso = str(meeting.get("meeting_date", ""))[:10]
    return resolve_minutes_url(
        minutes_index,
        iso,
        type_name=type_name,
        type_id=meeting.get("type_id"),
    ) or ""


def _build_title(type_display: str, meeting_date: str, doc: dict | None) -> str:
    if doc and doc.get("title"):
        return str(doc["title"])
    return f"{type_display} — {meeting_date}"


def _is_valid_coord_pair(lat: str, lon: str) -> bool:
    if not lat or not lon:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False
    return in_estero_bbox(lat_f, lon_f)


def build_gold(*, geocoded_location_ids: set[int] | None = None) -> dict[str, Any]:
    """Emit app/data/gold/meetings_public.csv and return a stage report."""
    meetings = _read_csv(config.SILVER_MEETINGS)
    documents = _read_csv(config.SILVER_DOCUMENTS)
    minutes_index = load_minutes_index()

    projects = _index_by_id(reference.projects(), "project_id")
    types = _index_by_id(reference.meeting_types(), "type_id")
    loc_by_id = _index_by_id(reference.locations(), "location_id")
    locs_by_project = _locations_by_project(reference.locations())
    docs_by_meeting = _documents_by_meeting(documents)

    rows: list[dict[str, str]] = []
    with_pdf = 0
    location_quality: dict[str, Any] = {
        "exact_location_id": 0,
        "project_fallback": 0,
        "geocoded": 0,
        "text_only": 0,
        "missing": 0,
        "with_coords": 0,
        "outside_bbox_or_invalid": 0,
        "strict_violations": [],
    }
    for m in meetings:
        pid = int(m["project_id"])
        tid = int(m["type_id"])
        project = projects.get(pid, {})
        mtype = types.get(tid, {})
        type_name = mtype.get("type_name", "")
        type_display = _meeting_type_display(type_name)
        meeting_date = str(m.get("meeting_date", ""))[:10]
        doc = docs_by_meeting.get(int(m["meeting_id"]))

        loc_name, lat, lon, confidence = _resolve_location(
            m,
            loc_by_id,
            locs_by_project,
            geocoded_location_ids=geocoded_location_ids,
        )
        location_quality[confidence] += 1
        has_coords = bool(lat and lon)
        if has_coords and _is_valid_coord_pair(lat, lon):
            location_quality["with_coords"] += 1
        elif has_coords:
            location_quality["outside_bbox_or_invalid"] += 1
            if len(location_quality["strict_violations"]) < 25:
                location_quality["strict_violations"].append(
                    f"meeting_id={m.get('meeting_id')} resolved outside ESTERO_BBOX or invalid coords"
                )
        elif confidence in {"text_only", "missing"}:
            if len(location_quality["strict_violations"]) < 25:
                location_quality["strict_violations"].append(
                    f"meeting_id={m.get('meeting_id')} has unresolved location confidence={confidence}"
                )
        minutes_url = _resolve_minutes_url_for_row(m, type_name, doc, minutes_index)
        if minutes_url:
            with_pdf += 1

        in_progress, in_progress_note = gold_in_progress_columns(m, doc)

        doc_date = ""
        if doc and doc.get("doc_date"):
            doc_date = str(doc["doc_date"])[:10]
        elif minutes_url:
            doc_date = meeting_date

        rows.append({
            "ProjectName": project.get("project_name", ""),
            "MeetingType": type_display,
            "MeetingDate": meeting_date,
            "MeetingYear": str(m.get("meeting_year", "")),
            "Status": m.get("status") or "Accepted",
            "Finalized": _meeting_finalized(m.get("status") or "", minutes_url),
            "InProgress": in_progress,
            "InProgressNote": in_progress_note,
            "ActionTaken": m.get("action_taken") or "",
            "StartTime": m.get("start_time") or "",
            "StaffCode": m.get("doc_ref_code") or "",
            "Title": _build_title(type_display, meeting_date, doc),
            "MinutesURL": minutes_url,
            "DocDate": doc_date,
            "LocationName": loc_name,
            "Latitude": lat,
            "Longitude": lon,
        })

    rows.sort(key=lambda r: (r["MeetingDate"], r["ProjectName"]), reverse=True)

    arcgis_report = build_arcgis_gold()
    arcgis_rows = _read_csv(config.GOLD_ARCGIS_PUBLIC) if config.GOLD_ARCGIS_PUBLIC.exists() else []
    rows, clean_stats = clean_meetings_public_rows(rows, arcgis_rows)

    _atomic_write_csv(config.GOLD_MEETINGS_PUBLIC, GOLD_FIELDS, rows)
    _atomic_write_json_compact(config.GOLD_MEETINGS_JSON, rows)

    shard_report = None
    if len(rows) >= config.GOLD_SHARD_THRESHOLD:
        shard_report = _write_year_shards(rows)
    else:
        _clear_year_shards()

    ai_report = build_ai_gold(arcgis_rows=arcgis_rows)
    site_manifest = _build_site_manifest(
        rows,
        shard_report=shard_report,
        arcgis_report=arcgis_report,
        ai_report=ai_report,
    )
    _atomic_write_json_compact(config.GOLD_SITE_MANIFEST, site_manifest)

    action_report = _build_gold_actions(meetings, projects, types)

    return {
        "rows": len(rows),
        "with_minutes_url": with_pdf,
        "path": _rel(config.GOLD_MEETINGS_PUBLIC),
        "json_path": _rel(config.GOLD_MEETINGS_JSON),
        "manifest_path": _rel(config.GOLD_SITE_MANIFEST),
        "delivery": site_manifest["delivery"],
        "shards": len(shard_report or []),
        "actions": action_report,
        "location_quality": location_quality,
        "arcgis": arcgis_report,
        "arcgis_clean": clean_stats,
        "ai": ai_report,
    }


def _read_meeting_actions() -> list[dict]:
    """Read silver meeting_actions.csv, returning [] if it hasn't been built."""
    if not config.SILVER_MEETING_ACTIONS.exists():
        return []
    return _read_csv(config.SILVER_MEETING_ACTIONS)


def _build_gold_actions(
    meetings: list[dict],
    projects: dict[int, dict],
    types: dict[int, dict],
) -> dict[str, Any]:
    """Emit the additive app/data/gold/meeting_actions_public.csv.

    Denormalizes each structured action with its meeting's date, project and
    type for the public frontend. Gracefully no-ops (writes an empty file) when
    silver meeting_actions are missing.
    """
    actions = _read_meeting_actions()
    meetings_by_id = _index_by_id(meetings, "meeting_id")

    rows: list[dict[str, str]] = []
    for a in actions:
        mid = a.get("meeting_id")
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            mid_int = None
        meeting = meetings_by_id.get(mid_int, {}) if mid_int is not None else {}
        project = projects.get(int(meeting["project_id"]), {}) if meeting.get("project_id") else {}
        mtype = types.get(int(meeting["type_id"]), {}) if meeting.get("type_id") else {}
        rows.append({
            "ActionId": a.get("action_id", ""),
            "MeetingId": mid if mid is not None else "",
            "MeetingDate": str(meeting.get("meeting_date", ""))[:10],
            "ProjectName": project.get("project_name", ""),
            "MeetingType": _meeting_type_display(mtype.get("type_name", "")),
            "Sequence": a.get("sequence", ""),
            "Kind": a.get("kind", ""),
            "ReferenceCode": a.get("reference_code", ""),
            "AmountUSD": a.get("amount_usd", ""),
            "RawText": a.get("raw_text", ""),
        })

    rows.sort(key=lambda r: (r["MeetingDate"], str(r["MeetingId"]), str(r["Sequence"])), reverse=True)
    _atomic_write_csv(config.GOLD_MEETING_ACTIONS_PUBLIC, GOLD_ACTION_FIELDS, rows)
    return {
        "rows": len(rows),
        "path": _rel(config.GOLD_MEETING_ACTIONS_PUBLIC),
    }
