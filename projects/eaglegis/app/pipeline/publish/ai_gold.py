"""
AI gold layer: agenda-item records with provenance and confidence metadata.

Designed so downstream LLM/RAG/training pipelines can ground answers in primary
sources and skip or flag rows that would invite hallucination.

Each row is one agenda item with atomic, non-collapsed fields (summary, action,
motion, vote counts, location) so ML pipelines can learn from specific facts
rather than merged summaries.

Inputs (when present in the repo):
  - normalized_csv_council/arcgis_agenda_map_data.csv (+ companion CSVs)
  - normalized_csv_pilot/pzdb_from_raw_verify/arcgis_agenda_map_data.csv (+ companion CSVs)

Outputs:
  - app/data/gold/meetings_ai_public.csv
  - app/data/gold/meetings_ai_public.jsonl
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.pipeline import config
from app.pipeline.load.silver import _read_csv

# Minimum geocode confidence before lat/lon are included in AI deliverables.
AI_GEOCODE_MIN_CONFIDENCE = 0.95

WEAK_ACTION_MARKERS = (
    "see minutes",
    "no action found",
    "meeting cancelled",
    "no action extracted",
)

APPLICATION_TYPE_LABELS: dict[str, str] = {
    "DOS": "development_order",
    "O": "ordinance",
    "R": "resolution",
    "EC": "engineering_certificate",
    "DCI": "development_compliance_inspection",
    "CN": "contract",
    "RFB": "request_for_bid",
    "RFQ": "request_for_quote",
    "LDO": "land_development_order",
    "ADD": "address_assignment",
}

AI_GOLD_FIELDS = [
    # Identity
    "RecordId",
    "SourceBoard",
    "DataGrain",
    "RecordType",
    "MeetingId",
    "ItemId",
    "MotionId",
    # Meeting context
    "Board",
    "MeetingFormat",
    "MeetingType",
    "MeetingDate",
    "MeetingYear",
    "MeetingTime",
    "MeetingVenue",
    "Status",
    # Agenda item
    "AgendaItemNumber",
    "AgendaItemType",
    "FactCategory",
    "LandUseCategory",
    "ProjectName",
    "ProjectTitle",
    "Summary",
    "ApplicationId",
    "ApplicationType",
    "ApplicantName",
    "District",
    "StaffCode",
    # Actions (kept separate — do not collapse for ML)
    "ActionTaken",
    "Outcome",
    "MotionText",
    "ProposedBy",
    "SecondedBy",
    "VoteResult",
    "VoteYes",
    "VoteNo",
    "VoteAbstain",
    # Location
    "AddressRaw",
    "AddressNormalized",
    "LocationName",
    "Latitude",
    "Longitude",
    "GeocodeConfidence",
    "LocationGrain",
    "ParcelId",
    # Provenance / ML quality gates
    "PrimarySourceUrl",
    "SourceFilename",
    "ExtractionMethod",
    "ExtractionConfidence",
    "ReviewRequired",
    "ReviewReason",
    "AiReady",
    "CitationText",
]

_SOURCE_SLUG = {
    "Village Council": "council",
    "Planning Zoning & Design Board": "pzdb",
}

_FACT_CATEGORY_BY_ITEM_TYPE: dict[str, str] = {
    "Ordinance": "legislative_ordinance",
    "Resolution": "legislative_resolution",
    "Contract Approval": "contract_approval",
    "Consent Agenda": "consent_agenda",
    "Vote": "board_vote",
    "Presentation": "presentation",
    "Public Hearing": "public_hearing",
    "Workshop": "workshop",
}


@dataclass
class SourceEnrichment:
    items_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    motions_by_item: dict[str, dict[str, Any]] = field(default_factory=dict)
    meetings_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    locations_by_item: dict[str, dict[str, Any]] = field(default_factory=dict)
    review_by_filename: dict[str, str] = field(default_factory=dict)


def _rel(path: Path) -> str:
    return path.relative_to(config.REPO_ROOT).as_posix()


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, separators=(",", ":"), default=str))
                f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _parse_confidence(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _clean_text(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def _is_weak_text(text: str) -> bool:
    if not text:
        return True
    low = text.lower()
    if len(low) < 12:
        return True
    return any(marker in low for marker in WEAK_ACTION_MARKERS)


def _board_slug(board: str) -> str:
    return _SOURCE_SLUG.get(board, re.sub(r"[^a-z0-9]+", "_", board.lower()).strip("_") or "other")


def _application_type(application_id: str) -> str:
    if not application_id:
        return ""
    match = re.match(r"^([A-Z]+)", application_id)
    if not match:
        return "other"
    prefix = match.group(1)
    return APPLICATION_TYPE_LABELS.get(prefix, prefix.lower())


def _fact_category(item_type: str, application_type: str) -> str:
    if item_type in _FACT_CATEGORY_BY_ITEM_TYPE:
        return _FACT_CATEGORY_BY_ITEM_TYPE[item_type]
    if application_type == "development_order":
        return "development_order"
    if application_type == "ordinance":
        return "legislative_ordinance"
    if application_type == "resolution":
        return "legislative_resolution"
    return "other"


def _load_source_enrichment(source_dir: Path, review_path: Path | None) -> SourceEnrichment:
    enrichment = SourceEnrichment()

    agenda_path = source_dir / "agenda_items.csv"
    if agenda_path.exists():
        for row in _read_csv(agenda_path):
            item_id = _clean_text(row.get("item_id"))
            if item_id:
                enrichment.items_by_id[item_id] = row

    motions_path = source_dir / "motions.csv"
    if motions_path.exists():
        for row in _read_csv(motions_path):
            item_id = _clean_text(row.get("item_id"))
            if item_id and item_id not in enrichment.motions_by_item:
                enrichment.motions_by_item[item_id] = row

    meetings_path = source_dir / "meetings_v2.csv"
    if meetings_path.exists():
        for row in _read_csv(meetings_path):
            meeting_id = _clean_text(row.get("meeting_id"))
            if meeting_id:
                enrichment.meetings_by_id[meeting_id] = row

    locations_path = source_dir / "locations_v2.csv"
    if locations_path.exists():
        for row in _read_csv(locations_path):
            item_id = _clean_text(row.get("item_id"))
            if item_id and item_id not in enrichment.locations_by_item:
                enrichment.locations_by_item[item_id] = row

    if review_path and review_path.exists():
        reasons_by_filename: dict[str, list[str]] = {}
        for row in _read_csv(review_path):
            reason = _clean_text(row.get("reason"))
            if not reason:
                continue
            fname = _clean_text(row.get("filename"))
            if fname:
                reasons_by_filename.setdefault(fname, []).append(reason)
        for fname, reasons in reasons_by_filename.items():
            enrichment.review_by_filename[fname] = "; ".join(dict.fromkeys(reasons))

    return enrichment


def _best_citation_action(*texts: str) -> str:
    for text in texts:
        cleaned = _clean_text(text)
        if cleaned and not _is_weak_text(cleaned):
            return cleaned
    for text in texts:
        cleaned = _clean_text(text)
        if cleaned:
            return cleaned
    return "See source minutes."


def _has_substantive_facts(*texts: str) -> bool:
    return any(_clean_text(t) and not _is_weak_text(_clean_text(t)) for t in texts)


def _extraction_confidence(
    *,
    review_required: bool,
    action_text: str,
    outcome_text: str,
    motion_text: str,
    summary_text: str,
    address: str,
    geocode_conf: float | None,
) -> str:
    substantive = _has_substantive_facts(action_text, outcome_text, motion_text, summary_text)
    if review_required or not substantive:
        return "low"
    has_address = bool(address)
    has_strong_geo = geocode_conf is not None and geocode_conf >= AI_GEOCODE_MIN_CONFIDENCE
    if has_address or has_strong_geo:
        return "high"
    if geocode_conf is not None and geocode_conf >= 0.7:
        return "medium"
    return "medium"


def _citation_text(row: dict[str, str]) -> str:
    board = row.get("Board") or "Meeting body"
    date = row.get("MeetingDate") or "unknown date"
    item_no = row.get("AgendaItemNumber") or "?"
    item_type = row.get("AgendaItemType") or "item"
    action = _best_citation_action(
        row.get("ActionTaken", ""),
        row.get("Outcome", ""),
        row.get("MotionText", ""),
        row.get("Summary", ""),
    )
    url = row.get("PrimarySourceUrl") or ""
    base = (
        f"{board} meeting on {date}, agenda item {item_no} ({item_type}): "
        f"{action}"
    )
    return f"{base} Source: {url}" if url else base


def _transform_arcgis_row(
    row: dict[str, Any],
    *,
    source_tag: str,
    enrichment: SourceEnrichment,
) -> dict[str, str]:
    board = _clean_text(row.get("Board"))
    agenda_id = _clean_text(row.get("AgendaItemID"))
    meeting_date = _clean_text(row.get("MeetingDate"))[:10]
    record_id = f"{_board_slug(board)}:{agenda_id}" if agenda_id else f"{_board_slug(board)}:{meeting_date}:unknown"

    item = enrichment.items_by_id.get(agenda_id, {})
    motion = enrichment.motions_by_item.get(agenda_id, {})
    location = enrichment.locations_by_item.get(agenda_id, {})
    meeting_id = _clean_text(item.get("meeting_id"))
    meeting = enrichment.meetings_by_id.get(meeting_id, {})

    filename = _clean_text(row.get("Filename") or meeting.get("filename"))
    review_reason = enrichment.review_by_filename.get(filename, "")
    review_required = bool(review_reason)

    action_taken = _clean_text(row.get("ActionTaken"))
    outcome = _clean_text(row.get("Outcome") or motion.get("outcome") or item.get("outcome"))
    motion_text = _clean_text(row.get("MotionText") or motion.get("motion_text") or item.get("motion_text"))
    summary = _clean_text(row.get("Summary") or item.get("summary"))
    proposed_by = _clean_text(row.get("ProposedBy") or motion.get("proposed_by"))
    seconded_by = _clean_text(row.get("SecondedBy") or motion.get("seconded_by"))
    vote_result = _clean_text(row.get("VoteResult") or item.get("vote_result"))
    vote_yes = _clean_text(motion.get("vote_yes"))
    vote_no = _clean_text(motion.get("vote_no"))
    vote_abstain = _clean_text(motion.get("vote_abstain"))

    address_raw = _clean_text(location.get("address_raw") or item.get("address_raw"))
    # ArcGIS agenda map data is the authoritative location source.
    address_normalized = _clean_text(
        row.get("Location") or row.get("LocationName")
        or location.get("address_normalized")
        or item.get("address_raw")
    )
    location_name = _clean_text(row.get("LocationName") or row.get("Location"))
    geocode_conf = _parse_confidence(row.get("GeocodeConfidence") or location.get("geocode_confidence"))
    lat_raw = _clean_text(row.get("Latitude") or location.get("latitude"))
    lon_raw = _clean_text(row.get("Longitude") or location.get("longitude"))
    parcel_id = _clean_text(location.get("parcel_id"))

    include_coords = (
        geocode_conf is not None
        and geocode_conf >= AI_GEOCODE_MIN_CONFIDENCE
        and lat_raw
        and lon_raw
    )

    application_id = _clean_text(row.get("ApplicationID") or item.get("application_id"))
    application_type = _application_type(application_id)
    agenda_item_type = _clean_text(row.get("AgendaItemType") or item.get("item_type"))
    fact_category = _fact_category(agenda_item_type, application_type)

    source_url = _clean_text(row.get("Document_Link") or meeting.get("pdf_url"))
    extraction_conf = _extraction_confidence(
        review_required=review_required,
        action_text=action_taken,
        outcome_text=outcome,
        motion_text=motion_text,
        summary_text=summary,
        address=address_normalized or address_raw,
        geocode_conf=geocode_conf,
    )

    ai_ready = (
        not review_required
        and extraction_conf == "high"
        and bool(source_url)
        and _has_substantive_facts(action_taken, outcome, motion_text, summary)
    )

    out: dict[str, str] = {
        "RecordId": record_id,
        "SourceBoard": source_tag,
        "DataGrain": "agenda_item",
        "RecordType": _clean_text(row.get("RecordType")) or "AgendaItemLocation",
        "MeetingId": meeting_id,
        "ItemId": agenda_id,
        "MotionId": _clean_text(motion.get("motion_id")),
        "Board": board,
        "MeetingFormat": _clean_text(row.get("MeetingFormat")),
        "MeetingType": _clean_text(row.get("MeetingType")),
        "MeetingDate": meeting_date,
        "MeetingYear": _clean_text(row.get("MeetingYear")),
        "MeetingTime": _clean_text(meeting.get("meeting_time")),
        "MeetingVenue": _clean_text(meeting.get("meeting_location")),
        "Status": _clean_text(row.get("Status") or meeting.get("status")),
        "AgendaItemNumber": _clean_text(row.get("AgendaItemNumber") or item.get("item_number")),
        "AgendaItemType": agenda_item_type,
        "FactCategory": fact_category,
        "LandUseCategory": _clean_text(row.get("LandUseCategory")),
        "ProjectName": _clean_text(row.get("ProjectName")),
        "ProjectTitle": _clean_text(row.get("ProjectTitle") or item.get("project_title")),
        "Summary": summary,
        "ApplicationId": application_id,
        "ApplicationType": application_type,
        "ApplicantName": _clean_text(row.get("ApplicantName") or item.get("applicant_name")),
        "District": _clean_text(row.get("District") or item.get("district")),
        "StaffCode": _clean_text(row.get("StaffCode")),
        "ActionTaken": action_taken,
        "Outcome": outcome,
        "MotionText": motion_text,
        "ProposedBy": proposed_by,
        "SecondedBy": seconded_by,
        "VoteResult": vote_result,
        "VoteYes": vote_yes,
        "VoteNo": vote_no,
        "VoteAbstain": vote_abstain,
        "AddressRaw": address_raw,
        "AddressNormalized": address_normalized,
        "LocationName": location_name,
        "Latitude": lat_raw if include_coords else "",
        "Longitude": lon_raw if include_coords else "",
        "GeocodeConfidence": "" if geocode_conf is None else str(geocode_conf),
        "LocationGrain": "item_address" if (address_normalized or address_raw) else "unknown",
        "ParcelId": parcel_id,
        "PrimarySourceUrl": source_url,
        "SourceFilename": filename,
        "ExtractionMethod": f"pdf_extraction:{source_tag}",
        "ExtractionConfidence": extraction_conf,
        "ReviewRequired": "true" if review_required else "false",
        "ReviewReason": review_reason,
        "AiReady": "true" if ai_ready else "false",
    }
    out["CitationText"] = _citation_text(out)
    return out


def _load_arcgis_sources() -> list[tuple[str, Path, Path]]:
    """Return (source_tag, arcgis_csv, source_dir)."""
    sources: list[tuple[str, Path, Path]] = []
    council_arcgis = config.NORMALIZED_COUNCIL_DIR / "arcgis_agenda_map_data.csv"
    if council_arcgis.exists():
        sources.append(("council", council_arcgis, config.NORMALIZED_COUNCIL_DIR))
    pzdb_arcgis = config.NORMALIZED_PZDB_DIR / "arcgis_agenda_map_data.csv"
    if pzdb_arcgis.exists():
        sources.append(("pzdb", pzdb_arcgis, config.NORMALIZED_PZDB_DIR))
    return sources


def _to_jsonl_record(csv_row: dict[str, str]) -> dict[str, Any]:
    """Rich JSONL row for RAG/training with explicit grounding contract."""
    geocode_conf = _parse_confidence(csv_row.get("GeocodeConfidence"))
    return {
        "record_id": csv_row["RecordId"],
        "source_board": csv_row["SourceBoard"],
        "data_grain": csv_row["DataGrain"],
        "record_type": csv_row["RecordType"],
        "ids": {
            "meeting_id": csv_row["MeetingId"] or None,
            "item_id": csv_row["ItemId"] or None,
            "motion_id": csv_row["MotionId"] or None,
        },
        "meeting": {
            "board": csv_row["Board"],
            "format": csv_row["MeetingFormat"],
            "type": csv_row["MeetingType"],
            "date": csv_row["MeetingDate"],
            "year": csv_row["MeetingYear"],
            "time": csv_row["MeetingTime"] or None,
            "venue": csv_row["MeetingVenue"] or None,
            "status": csv_row["Status"],
        },
        "agenda_item": {
            "number": csv_row["AgendaItemNumber"],
            "type": csv_row["AgendaItemType"],
            "fact_category": csv_row["FactCategory"],
            "land_use_category": csv_row["LandUseCategory"] or None,
            "project_name": csv_row["ProjectName"],
            "title": csv_row["ProjectTitle"],
            "summary": csv_row["Summary"],
            "application_id": csv_row["ApplicationId"] or None,
            "application_type": csv_row["ApplicationType"] or None,
            "applicant": csv_row["ApplicantName"] or None,
            "district": csv_row["District"] or None,
            "staff_code": csv_row["StaffCode"] or None,
        },
        "facts": {
            "action_taken": csv_row["ActionTaken"],
            "outcome": csv_row["Outcome"],
            "motion_text": csv_row["MotionText"],
            "proposed_by": csv_row["ProposedBy"] or None,
            "seconded_by": csv_row["SecondedBy"] or None,
            "vote_result": csv_row["VoteResult"] or None,
            "vote_yes": csv_row["VoteYes"] or None,
            "vote_no": csv_row["VoteNo"] or None,
            "vote_abstain": csv_row["VoteAbstain"] or None,
        },
        "location": {
            "address_raw": csv_row["AddressRaw"] or None,
            "address_normalized": csv_row["AddressNormalized"] or None,
            "name": csv_row["LocationName"] or None,
            "latitude": csv_row["Latitude"] or None,
            "longitude": csv_row["Longitude"] or None,
            "geocode_confidence": geocode_conf,
            "grain": csv_row["LocationGrain"],
            "parcel_id": csv_row["ParcelId"] or None,
        },
        "grounding": {
            "primary_source_url": csv_row["PrimarySourceUrl"],
            "source_filename": csv_row["SourceFilename"],
            "citation": csv_row["CitationText"],
            "extraction_method": csv_row["ExtractionMethod"],
            "extraction_confidence": csv_row["ExtractionConfidence"],
            "review_required": csv_row["ReviewRequired"] == "true",
            "review_reason": csv_row["ReviewReason"] or None,
            "ai_ready": csv_row["AiReady"] == "true",
            "instruction": (
                "Use only fields in this record and primary_source_url. "
                "Treat summary, action_taken, outcome, and motion_text as distinct "
                "extracted facts — do not merge or infer beyond them. "
                "If ai_ready is false, do not use this record for factual claims."
            ),
        },
    }


def _source_tag_for_board(board: str) -> str:
    return "pzdb" if "Planning" in (board or "") else "council"


def build_ai_gold(*, arcgis_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Emit AI gold CSV + JSONL from cleaned ArcGIS agenda-item rows."""
    enrichments: dict[str, SourceEnrichment] = {}
    if config.NORMALIZED_COUNCIL_DIR.exists():
        enrichments["council"] = _load_source_enrichment(
            config.NORMALIZED_COUNCIL_DIR,
            config.NORMALIZED_COUNCIL_DIR / "extraction_review.csv",
        )
    if config.NORMALIZED_PZDB_DIR.exists():
        enrichments["pzdb"] = _load_source_enrichment(config.NORMALIZED_PZDB_DIR, None)

    if arcgis_rows is None:
        arcgis_rows = []
        for source_tag, arcgis_path, source_dir in _load_arcgis_sources():
            if arcgis_path.exists():
                arcgis_rows.extend(_read_csv(arcgis_path))

    if not arcgis_rows:
        _atomic_write_csv(config.GOLD_AI_PUBLIC, AI_GOLD_FIELDS, [])
        _atomic_write_jsonl(config.GOLD_AI_JSONL, [])
        return {
            "rows": 0,
            "ai_ready": 0,
            "review_required": 0,
            "sources": [],
            "path": _rel(config.GOLD_AI_PUBLIC),
            "jsonl_path": _rel(config.GOLD_AI_JSONL),
            "skipped": "no arcgis_agenda_map_data.csv inputs found",
        }

    rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    source_report: list[dict[str, Any]] = []
    per_source_counts: dict[str, int] = defaultdict(int)

    for raw in arcgis_rows:
        if _clean_text(raw.get("RecordType")) and _clean_text(raw.get("RecordType")) != "AgendaItemLocation":
            continue
        source_tag = _source_tag_for_board(str(raw.get("Board") or ""))
        enrichment = enrichments.get(source_tag, SourceEnrichment())
        transformed = _transform_arcgis_row(
            raw,
            source_tag=source_tag,
            enrichment=enrichment,
        )
        rid = transformed["RecordId"]
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        rows.append(transformed)
        per_source_counts[source_tag] += 1

    for tag, count in per_source_counts.items():
        source_report.append({
            "tag": tag,
            "path": _rel(config.GOLD_ARCGIS_PUBLIC),
            "output_rows": count,
        })

    rows.sort(key=lambda r: (r["MeetingDate"], r["Board"], r["ItemId"]), reverse=True)
    _atomic_write_csv(config.GOLD_AI_PUBLIC, AI_GOLD_FIELDS, rows)
    jsonl_rows = [_to_jsonl_record(r) for r in rows]
    _atomic_write_jsonl(config.GOLD_AI_JSONL, jsonl_rows)

    ai_ready = sum(1 for r in rows if r["AiReady"] == "true")
    review_required = sum(1 for r in rows if r["ReviewRequired"] == "true")

    return {
        "rows": len(rows),
        "ai_ready": ai_ready,
        "review_required": review_required,
        "sources": source_report,
        "path": _rel(config.GOLD_AI_PUBLIC),
        "jsonl_path": _rel(config.GOLD_AI_JSONL),
    }
