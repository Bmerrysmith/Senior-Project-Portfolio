"""
Classify bronze (and silver) meeting rows as in progress vs complete vs closed.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from app.pipeline import config, reference
from app.pipeline.extract.meetings import normalize_body, normalize_iso

REASON_PZDB_PROJECT_MAPPING = "pzdb_project_mapping"
REASON_FUTURE_PLACEHOLDER = "future_placeholder"
REASON_FUTURE_SCHEDULED = "future_scheduled"
REASON_PENDING_STATUS = "pending_status"

REASON_TEXT: dict[str, str] = {
    REASON_PZDB_PROJECT_MAPPING: (
        "PZ&DB project and location mapping in EagleGIS is still in progress; "
        "individual development projects are not fully catalogued yet. "
        "Residents can still comment through Engage Estero or Village eComment."
    ),
    REASON_FUTURE_PLACEHOLDER: (
        "Bronze row is a placeholder for a PZ&DB meeting that has not been held yet."
    ),
    REASON_FUTURE_SCHEDULED: (
        "Meeting date is in the future — the public process has not concluded."
    ),
    REASON_PENDING_STATUS: (
        "Bronze status is Pending — outcome and project linkage are still being entered."
    ),
}

PROGRESS_IN_PROGRESS = "in_progress"
PROGRESS_COMPLETE = "complete"
PROGRESS_CLOSED = "closed"

IN_PROGRESS_MEETINGS = config.IN_PROGRESS_MEETINGS

IN_PROGRESS_FIELDS = [
    "record_id",
    "bronze_source_file",
    "body",
    "type_id",
    "project_id",
    "meeting_date",
    "bronze_status",
    "link_status",
    "progress_state",
    "in_progress_reasons",
    "description",
]


def _today_iso() -> str:
    return date.today().isoformat()


def pzdb_project_mapping_in_progress() -> bool:
    for proj in reference.projects():
        if int(proj.get("project_id", 0)) == 4:
            return (proj.get("data_status") or "").strip().lower() == "in_progress"
    return False


def _is_future_placeholder(link_status: str | None) -> bool:
    return (link_status or "").strip().lower() == config.FUTURE_PLACEHOLDER_TAG.lower()


def collect_in_progress_reasons(
    *,
    body: str | None,
    meeting_date: Any,
    status: str | None,
    link_status: str | None,
    project_id: Any = None,
    bronze_source_file: str | None = None,
    pzdb_mapping_active: bool | None = None,
) -> list[str]:
    if pzdb_mapping_active is None:
        pzdb_mapping_active = pzdb_project_mapping_in_progress()

    reasons: list[str] = []
    iso = normalize_iso(meeting_date)

    if _is_future_placeholder(link_status):
        reasons.append(REASON_FUTURE_PLACEHOLDER)
    if iso and iso > _today_iso():
        reasons.append(REASON_FUTURE_SCHEDULED)
    if (status or "").strip().lower() == "pending":
        reasons.append(REASON_PENDING_STATUS)

    is_pzdb_row = (
        body == "pzdb"
        or str(project_id or "") == "4"
        or (bronze_source_file or "") == "documents.csv"
    )
    if pzdb_mapping_active and is_pzdb_row and REASON_PZDB_PROJECT_MAPPING not in reasons:
        reasons.append(REASON_PZDB_PROJECT_MAPPING)

    seen: set[str] = set()
    out: list[str] = []
    for code in reasons:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def assess_progress(
    *,
    body: str | None,
    meeting_date: Any,
    status: str | None,
    link_status: str | None = None,
    project_id: Any = None,
    bronze_source_file: str | None = None,
    pzdb_mapping_active: bool | None = None,
) -> tuple[str, list[str], str]:
    st = (status or "").strip().lower()
    if st == "cancelled":
        return (
            PROGRESS_CLOSED,
            [],
            "Meeting was cancelled; no active public process.",
        )

    reasons = collect_in_progress_reasons(
        body=body,
        meeting_date=meeting_date,
        status=status,
        link_status=link_status,
        project_id=project_id,
        bronze_source_file=bronze_source_file,
        pzdb_mapping_active=pzdb_mapping_active,
    )
    if reasons:
        desc_parts = [REASON_TEXT[c] for c in reasons if c in REASON_TEXT]
        return (
            PROGRESS_IN_PROGRESS,
            reasons,
            " ".join(desc_parts),
        )
    return (
        PROGRESS_COMPLETE,
        [],
        "No in-progress flags; record is treated as complete in EagleGIS.",
    )


def assess_silver_meeting(
    meeting: dict[str, Any],
    document: dict[str, Any] | None = None,
    *,
    pzdb_mapping_active: bool | None = None,
) -> tuple[str, list[str], str]:
    type_name = document.get("type_name") if document else None
    body = normalize_body(meeting.get("type_id")) or normalize_body(type_name)
    link_status = document.get("link_status") if document else None
    return assess_progress(
        body=body,
        meeting_date=meeting.get("meeting_date"),
        status=meeting.get("status"),
        link_status=link_status,
        project_id=meeting.get("project_id"),
        bronze_source_file="documents.csv" if body == "pzdb" else "meetings.csv",
        pzdb_mapping_active=pzdb_mapping_active,
    )


def gold_in_progress_columns(
    meeting: dict[str, Any],
    document: dict[str, Any] | None = None,
) -> tuple[str, str]:
    state, _reasons, description = assess_silver_meeting(meeting, document)
    if state == PROGRESS_IN_PROGRESS:
        return "Yes", description
    return "No", ""


def _read_bronze(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def catalog_bronze_in_progress(
    *,
    pzdb_mapping_active: bool | None = None,
) -> list[dict[str, str]]:
    if pzdb_mapping_active is None:
        pzdb_mapping_active = pzdb_project_mapping_in_progress()

    rows: list[dict[str, str]] = []

    for src, path, default_body in (
        ("meetings.csv", config.BRONZE_MEETINGS, "council"),
        ("documents.csv", config.BRONZE_DOCUMENTS, "pzdb"),
    ):
        for raw in _read_bronze(path):
            body = normalize_body(raw.get("type_id") or raw.get("type_name")) or default_body
            state, reasons, description = assess_progress(
                body=body,
                meeting_date=raw.get("meeting_date") or raw.get("doc_date"),
                status=raw.get("status"),
                link_status=raw.get("link_status"),
                project_id=raw.get("project_id"),
                bronze_source_file=src,
                pzdb_mapping_active=pzdb_mapping_active,
            )
            record_id = raw.get("meeting_id") if src == "meetings.csv" else raw.get("document_id")
            rows.append({
                "record_id": str(record_id or ""),
                "bronze_source_file": src,
                "body": body or "",
                "type_id": str(raw.get("type_id") or ""),
                "project_id": str(raw.get("project_id") or ""),
                "meeting_date": str(raw.get("meeting_date") or raw.get("doc_date") or "")[:10],
                "bronze_status": str(raw.get("status") or ""),
                "link_status": str(raw.get("link_status") or ""),
                "progress_state": state,
                "in_progress_reasons": "|".join(reasons),
                "description": description,
            })

    rows.sort(key=lambda r: (r["progress_state"] != PROGRESS_IN_PROGRESS, r["body"], r["meeting_date"]))
    return rows


def write_in_progress_csv(rows: list[dict[str, str]], out_path: Path | None = None) -> Path:
    target = out_path or IN_PROGRESS_MEETINGS
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=IN_PROGRESS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in IN_PROGRESS_FIELDS})
    return target


def collect_in_progress_meetings(out_path: Path | None = None) -> dict[str, Any]:
    rows = catalog_bronze_in_progress()
    target = write_in_progress_csv(rows, out_path)
    in_prog = [r for r in rows if r["progress_state"] == PROGRESS_IN_PROGRESS]
    by_reason: dict[str, int] = {}
    for r in in_prog:
        for code in filter(None, (r.get("in_progress_reasons") or "").split("|")):
            by_reason[code] = by_reason.get(code, 0) + 1
    return {
        "path": str(target),
        "total_bronze_rows": len(rows),
        "in_progress": len(in_prog),
        "complete": sum(1 for r in rows if r["progress_state"] == PROGRESS_COMPLETE),
        "closed": sum(1 for r in rows if r["progress_state"] == PROGRESS_CLOSED),
        "by_reason": by_reason,
        "pzdb_mapping_active": pzdb_project_mapping_in_progress(),
    }
