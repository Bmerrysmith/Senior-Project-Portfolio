"""
Clean gold deliverables using arcgis_agenda_map_data.csv as the location source of truth.

Normalized ArcGIS rows carry item-level geocoded addresses. Gold meetings_public
rows often fall back to project centroids or Council Chambers — this module
overlays accurate ArcGIS locations when a meeting date + board match exists.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

# Location names that indicate a coarse gold fallback, not a site address.
_GENERIC_LOCATION_MARKERS = (
    "council chambers",
    "village hall",
    "village of estero council",
    "bert rail trail",
    "corridor",
    "septic area",
    "uep",
    "road widening",
    "improvements",
    "parkway improvements",
)


def _parse_confidence(raw: Any) -> float:
    if raw in (None, ""):
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _fmt_coord(val: Any) -> str:
    if val in (None, ""):
        return ""
    try:
        return str(float(val))
    except (TypeError, ValueError):
        return str(val)


def board_for_meeting_type(meeting_type_display: str) -> str | None:
    """Map frontend meeting-type label to ArcGIS Board name."""
    low = (meeting_type_display or "").lower()
    if "pzdb" in low or ("planning" in low and "zoning" in low):
        return "Planning Zoning & Design Board"
    if any(token in low for token in ("council", "workshop", "hearing", "joint", "strategic")):
        return "Village Council"
    return None


def index_arcgis_by_meeting(arcgis_rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group ArcGIS agenda rows by (MeetingDate, Board)."""
    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in arcgis_rows:
        date = str(row.get("MeetingDate") or row.get("ArcGIS_Date") or "")[:10]
        board = str(row.get("Board") or "").strip()
        if date and board:
            out[(date, board)].append(row)
    return out


def _is_generic_location(name: str) -> bool:
    low = (name or "").lower().strip()
    if not low:
        return True
    return any(marker in low for marker in _GENERIC_LOCATION_MARKERS)


def pick_best_arcgis_location(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the ArcGIS row with the best geocoded site location."""
    with_coords = [
        item for item in items
        if item.get("Latitude") not in (None, "") and item.get("Longitude") not in (None, "")
    ]
    if not with_coords:
        return None
    return max(
        with_coords,
        key=lambda row: (
            _parse_confidence(row.get("GeocodeConfidence")),
            len(str(row.get("Location") or row.get("LocationName") or "")),
        ),
    )


def _merge_arcgis_actions(items: list[dict[str, Any]], *, max_parts: int = 6) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for item in items:
        for key in ("ActionTaken", "Outcome", "Summary"):
            text = str(item.get(key) or "").strip()
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            parts.append(text)
            if len(parts) >= max_parts:
                break
        if len(parts) >= max_parts:
            break
    return " | ".join(parts)


def _is_weak_action(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return True
    low = text.lower()
    return low in ("see minutes", "no action found", "meeting cancelled")


def clean_meetings_public_rows(
    meeting_rows: list[dict[str, str]],
    arcgis_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """
    Overlay ArcGIS locations (and optionally actions/URLs) onto gold meeting rows.

    Keeps the 14-column schema and row count unchanged.
    """
    by_meeting = index_arcgis_by_meeting(arcgis_rows)
    stats = {
        "matched": 0,
        "locations_updated": 0,
        "actions_updated": 0,
        "minutes_updated": 0,
    }

    cleaned: list[dict[str, str]] = []
    for row in meeting_rows:
        out = dict(row)
        board = board_for_meeting_type(out.get("MeetingType", ""))
        if not board:
            cleaned.append(out)
            continue

        items = by_meeting.get((out.get("MeetingDate", "")[:10], board), [])
        if not items:
            cleaned.append(out)
            continue

        stats["matched"] += 1
        best = pick_best_arcgis_location(items)
        if best:
            arc_loc = str(best.get("Location") or best.get("LocationName") or "").strip()
            arc_lat = _fmt_coord(best.get("Latitude"))
            arc_lon = _fmt_coord(best.get("Longitude"))
            current_loc = str(out.get("LocationName") or "").strip()

            if arc_loc and (_is_generic_location(current_loc) or arc_loc != current_loc):
                out["LocationName"] = arc_loc
                stats["locations_updated"] += 1
            if arc_lat and arc_lon:
                out["Latitude"] = arc_lat
                out["Longitude"] = arc_lon

        merged_action = _merge_arcgis_actions(items)
        if merged_action and _is_weak_action(out.get("ActionTaken", "")):
            out["ActionTaken"] = merged_action
            stats["actions_updated"] += 1

        doc_link = str(items[0].get("Document_Link") or "").strip()
        if doc_link and not str(out.get("MinutesURL") or "").strip():
            out["MinutesURL"] = doc_link
            stats["minutes_updated"] += 1

        cleaned.append(out)

    return cleaned, stats
