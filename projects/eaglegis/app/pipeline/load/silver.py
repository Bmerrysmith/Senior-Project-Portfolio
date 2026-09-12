"""
Silver-layer build step.

Reads bronze CSVs (``app/data/meetings.csv`` and ``app/data/documents.csv``),
validates and cleans each row, and writes:

  * ``app/data/silver/meetings.csv``           — validated meetings, cleaned text,
                                                 plus PZ&DB meetings synthesized
                                                 from the document feed (see
                                                 "Derived meetings" below)
  * ``app/data/silver/documents.csv``          — real (non-placeholder) documents
  * ``app/data/silver/documents_planned.csv``  — future placeholder rows kept
                                                 separately so analytics never
                                                 mixes them with real data
  * ``app/data/silver/_rejects.json``          — rows that failed validation

Derived meetings
----------------
The bronze ``meetings.csv`` covers Village Council meetings (``type_id=1``)
only. The bronze ``documents.csv`` is Planning Zoning & Design Board
(``type_id=2``) meeting minutes, with one document per PZ&DB meeting and
no overlap in either ``meeting_id`` or ``meeting_date`` with Village
Council. To make documents FK-valid against the meetings table (and to
correctly track PZ&DB meetings as first-class rows), silver synthesizes
one PZ&DB meeting per unique ``meeting_id`` in documents. The defaults
are deterministic: ``project_id=4`` ("PZ&DB General Meeting Records",
which exists for exactly this purpose), ``type_id=2``, ``location_id=6``
("Village of Estero Council Chambers"), and ``filename`` derived from
the document's ``file_url``.

Returns a stage report dict that the orchestrator includes in the run manifest.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.pipeline import config, reference
from app.pipeline.clean.actions import parse_actions
from app.pipeline.clean.text import clean_action_text
from app.pipeline.collect.minutes import load_minutes_index, resolve_minutes_url
from app.pipeline.validate.schemas import (
    DocumentRow,
    MeetingRow,
    validate_rows,
)

# When we synthesize a meeting for a document, we map the document's
# ``type_name`` to a stable (type_id, project_id, location_id) triple.
# Today the only document feed is PZ&DB, but new feeds can register here.
SYNTHESIZED_MEETING_DEFAULTS: dict[str, dict[str, int]] = {
    "Planning Zoning & Design Board": {
        "type_id": 2,
        "project_id": 4,      # "PZ&DB General Meeting Records"
        "location_id": 6,     # "Village of Estero Council Chambers"
    },
}
SYNTHESIZED_MEETING_LOCATION_NAME = "Village of Estero Council Chambers"

MEETING_OUT_FIELDS = [
    "meeting_id", "project_id", "type_id", "meeting_date", "meeting_year",
    "location", "start_time", "end_time", "action_taken", "status",
    "approved_by_council_date", "doc_ref_code", "filename", "notes",
    "location_id",
]

DOCUMENT_OUT_FIELDS = [
    "document_id", "meeting_id", "title", "file_url", "doc_date",
    "meeting_date", "meeting_year", "status", "type_name", "link_status",
]

MEETING_ACTION_OUT_FIELDS = [
    "action_id", "meeting_id", "sequence", "kind",
    "reference_code", "amount_usd", "raw_text",
]


def build_meeting_actions(meeting_dicts: list[dict]) -> list[dict]:
    """Explode each meeting's ``action_taken`` blob into structured rows.

    ``action_id`` is a stable sequential int assigned in meeting order (which
    is itself deterministic) then by within-meeting ``sequence``. Meetings with
    no parseable actions contribute no rows.
    """
    rows: list[dict] = []
    action_id = 1
    for m in meeting_dicts:
        mid = m.get("meeting_id")
        for record in parse_actions(m.get("action_taken")):
            rows.append({
                "action_id": action_id,
                "meeting_id": mid,
                "sequence": record["sequence"],
                "kind": record["kind"],
                "reference_code": record["reference_code"],
                "amount_usd": record["amount_usd"],
                "raw_text": record["raw_text"],
            })
            action_id += 1
    return rows


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _atomic_write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Write to a tempfile in the same directory then rename, so a crashed
    pipeline never leaves a half-written silver file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            # Use LF line endings so CI rebuild diffs are deterministic across OSes.
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _meeting_to_dict(m: MeetingRow) -> dict:
    d = m.model_dump()
    d["action_taken"] = clean_action_text(d.get("action_taken"))
    d["notes"] = clean_action_text(d.get("notes"))
    return d


def _is_future_placeholder(d: DocumentRow) -> bool:
    return (d.link_status or "").strip().lower() == config.FUTURE_PLACEHOLDER_TAG.lower()


def _filename_from_url(url: str | None) -> str | None:
    """Derive a clean filename from a document URL.

    Returns e.g. ``"12092025 PZDB Minutes.pdf"`` from a URL ending in
    ``"12092025%20PZDB%20Minutes.pdf"``. Returns None for empty input.
    """
    if not url:
        return None
    path = urlparse(url).path
    name = unquote(Path(path).name).strip()
    return name or None


def _synthesize_pzdb_meetings_from_documents(
    document_dicts: list[dict],
    existing_meeting_ids: set[int],
) -> tuple[list[dict], list[dict]]:
    """For every doc whose ``meeting_id`` isn't already a real meeting,
    emit a synthetic PZ&DB meeting row so the FK is satisfied downstream.

    Returns ``(synth_meeting_dicts, rejects)``. Rejects carry documents
    we couldn't synthesize a meeting for (e.g. unknown ``type_name``
    or missing ``meeting_date``); the caller appends them to the
    standard rejects file.

    Idempotent: a document whose ``meeting_id`` already exists in
    ``existing_meeting_ids`` is skipped silently — synthesis runs after
    bronze meetings are loaded, so collisions don't happen by default
    but the guard is here in case future data overlaps.
    """
    synth: dict[int, dict] = {}   # by meeting_id, so duplicate docs collapse
    rejects: list[dict] = []
    for d in document_dicts:
        mid = d.get("meeting_id")
        if mid is None or mid in existing_meeting_ids or mid in synth:
            continue
        type_name = (d.get("type_name") or "").strip()
        defaults = SYNTHESIZED_MEETING_DEFAULTS.get(type_name)
        if defaults is None:
            rejects.append({
                "row": d,
                "errors": [
                    f"cannot synthesize meeting for unknown type_name="
                    f"{type_name!r}; add it to SYNTHESIZED_MEETING_DEFAULTS"
                ],
            })
            continue
        if not d.get("meeting_date"):
            rejects.append({
                "row": d,
                "errors": ["cannot synthesize meeting: meeting_date is empty"],
            })
            continue
        synth[mid] = {
            "meeting_id": mid,
            "project_id": defaults["project_id"],
            "type_id": defaults["type_id"],
            "meeting_date": d["meeting_date"],
            "meeting_year": d.get("meeting_year") or d["meeting_date"].year,
            "location": SYNTHESIZED_MEETING_LOCATION_NAME,
            "start_time": None,
            "end_time": None,
            "action_taken": None,
            # The document's status (e.g. "Pending", "Missing / Not Uploaded")
            # describes the *document*, not the meeting. We use the same
            # default the bronze validator uses for meetings.
            "status": "Accepted",
            "approved_by_council_date": None,
            "doc_ref_code": None,
            "filename": _filename_from_url(d.get("file_url")),
            "notes": "Derived from document feed (no bronze meetings row).",
            "location_id": defaults["location_id"],
        }
    # Sort by meeting_id so the silver output is deterministic.
    return [synth[k] for k in sorted(synth)], rejects


def _check_unique(rows: list[dict], key: str) -> list[dict]:
    """Return a list of duplicate-key error reports."""
    seen: dict[Any, int] = {}
    dups: list[dict] = []
    for i, row in enumerate(rows):
        k = row.get(key)
        if k is None:
            continue
        if k in seen:
            dups.append({"row": row, "errors": [f"duplicate {key}={k} (also at row {seen[k]})"]})
        else:
            seen[k] = i
    return dups


def _enrich_documents_from_minutes_index(document_dicts: list[dict]) -> dict[str, int]:
    """Replace document URLs with canonical estero-fl.gov PDFs when the index has them."""
    index = load_minutes_index()
    stats = {"confirmed": 0, "still_missing": 0}
    for d in document_dicts:
        iso = str(d.get("meeting_date") or "")[:10]
        type_name = d.get("type_name")
        canonical = resolve_minutes_url(index, iso, type_name=type_name)
        if canonical:
            d["file_url"] = canonical
            d["link_status"] = "Uploaded"
            stats["confirmed"] += 1
        elif d.get("file_url"):
            d["link_status"] = "Missing / Not Uploaded"
            stats["still_missing"] += 1
    return stats


def build_silver() -> dict:
    """Run the bronze -> silver step end-to-end and return a report."""
    raw_meetings = _read_csv(config.BRONZE_MEETINGS)
    raw_documents = _read_csv(config.BRONZE_DOCUMENTS)

    valid_meetings, meeting_rejects = validate_rows(raw_meetings, MeetingRow)
    valid_documents, document_rejects = validate_rows(raw_documents, DocumentRow)

    meeting_dicts = [_meeting_to_dict(m) for m in valid_meetings]
    meeting_rejects.extend(_check_unique(meeting_dicts, "meeting_id"))

    document_dicts = [d.model_dump() for d in valid_documents]
    document_rejects.extend(_check_unique(document_dicts, "document_id"))
    minutes_doc_stats = _enrich_documents_from_minutes_index(document_dicts)

    bronze_meeting_ids = {m["meeting_id"] for m in meeting_dicts}
    synth_meetings, synth_rejects = _synthesize_pzdb_meetings_from_documents(
        document_dicts, bronze_meeting_ids,
    )
    document_rejects.extend(synth_rejects)
    meeting_dicts.extend(synth_meetings)

    valid_meeting_ids = {m["meeting_id"] for m in meeting_dicts}
    fk_warnings = [
        {"row": d, "errors": [f"unknown meeting_id={d['meeting_id']} (kept anyway)"]}
        for d in document_dicts if d["meeting_id"] not in valid_meeting_ids
    ]
    location_warnings = [
        {
            "row": m,
            "errors": ["missing location_id (using fallback resolution in gold)"],
        }
        for m in meeting_dicts
        if m.get("location_id") in (None, "") and (m.get("location") or "").strip()
    ]
    location_errors = [
        {
            "row": m,
            "errors": ["missing both location_id and location text"],
        }
        for m in meeting_dicts
        if m.get("location_id") in (None, "") and not (m.get("location") or "").strip()
    ]

    real_docs = [d for d in document_dicts if not _is_future_placeholder_dict(d)]
    planned_docs = [d for d in document_dicts if _is_future_placeholder_dict(d)]

    meeting_actions = build_meeting_actions(meeting_dicts)

    _atomic_write_csv(config.SILVER_MEETINGS, MEETING_OUT_FIELDS, meeting_dicts)
    _atomic_write_csv(config.SILVER_DOCUMENTS, DOCUMENT_OUT_FIELDS, real_docs)
    _atomic_write_csv(config.SILVER_DOCUMENTS_PLANNED, DOCUMENT_OUT_FIELDS, planned_docs)
    _atomic_write_csv(
        config.SILVER_MEETING_ACTIONS, MEETING_ACTION_OUT_FIELDS, meeting_actions,
    )
    _atomic_write_json(
        config.SILVER_REJECTS,
        {
            "meetings": meeting_rejects,
            "documents": document_rejects,
            "document_fk_warnings": fk_warnings,
            "location_warnings": location_warnings,
            "location_errors": location_errors,
        },
    )

    return {
        "meetings": {
            "in": len(raw_meetings),
            "out": len(meeting_dicts),
            "out_bronze": len(meeting_dicts) - len(synth_meetings),
            "out_synthesized": len(synth_meetings),
            "rejects": len(meeting_rejects),
        },
        "documents": {
            "in": len(raw_documents),
            "out_real": len(real_docs),
            "out_planned": len(planned_docs),
            "rejects": len(document_rejects),
            "fk_warnings": len(fk_warnings),
            "minutes_confirmed": minutes_doc_stats["confirmed"],
            "minutes_still_missing": minutes_doc_stats["still_missing"],
        },
        "meeting_actions": {
            "out": len(meeting_actions),
        },
        "locations": {
            "warnings": len(location_warnings),
            "errors": len(location_errors),
        },
    }


def _is_future_placeholder_dict(d: dict) -> bool:
    return (d.get("link_status") or "").strip().lower() == config.FUTURE_PLACEHOLDER_TAG.lower()
