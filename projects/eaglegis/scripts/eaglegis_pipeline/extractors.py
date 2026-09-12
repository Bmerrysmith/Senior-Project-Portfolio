from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d")


MEETING_TYPE_ALIASES = {
    "regular council meeting": "Village Council Regular Meeting",
    "village council meeting": "Village Council Regular Meeting",
    "village council regular meeting": "Village Council Regular Meeting",
    "pzdb meeting": "Planning Zoning & Design Board",
    "planning zoning & design board": "Planning Zoning & Design Board",
    "planning, zoning & design board": "Planning Zoning & Design Board",
    "planning zoning and design board": "Planning Zoning & Design Board",
    "special called meeting": "Special Meeting",
}


@dataclass(frozen=True)
class AgendaEntry:
    title: str | None
    action_text: str
    vote_text: str | None = None


def normalize_meeting_type(value: str | None) -> str | None:
    if not value:
        return None
    key = re.sub(r"\s+", " ", value.strip().lower())
    return MEETING_TYPE_ALIASES.get(key, value.strip())


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().replace(",", ", ")
    value = re.sub(r"\s+", " ", value)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.title(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def extract_date(filename: str, text: str) -> tuple[str | None, str]:
    match = re.search(r"(?:The\s+)?([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", text, re.I)
    if match:
        parsed = parse_date(" ".join(match.groups()))
        if parsed:
            return parsed, "pdf_text"

    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}", "filename"

    match = re.search(r"(?<!\d)(20\d{2})(\d{2})-(\d{2})(?!\d)", filename)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat(), "filename"
        except ValueError:
            return None, "missing"

    match = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", filename)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat(), "filename"
        except ValueError:
            return None, "missing"

    match = re.search(r"(?<!\d)(\d{1,2})(\d{2})(20\d{2})(?!\d)", filename)
    if match:
        month, day, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat(), "filename"
        except ValueError:
            return None, "missing"

    match = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2,4})(?!\d)", filename)
    if match:
        month, day, year = match.groups()
        year = f"20{year}" if len(year) == 2 else year
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat(), "filename"
        except ValueError:
            return None, "missing"

    return None, "missing"


def extract_start_time(text: str) -> str | None:
    patterns = [
        r"(?:Call to Order|Started|Order)(?:\s+at)?[:\s]+(\d{1,2}[:.]\d{2}\s*[ap]\.?m\.?)",
        r"\b(\d{1,2}[:.]\d{2}\s*[ap]\.?m\.?)\b",
    ]
    return _first_time(text, patterns)


def extract_end_time(text: str) -> str | None:
    patterns = [
        r"(?:Adjourned|Adjournment|Time Adjourned|Ended)(?:\s+at)?[:\s]+(\d{1,2}[:.]\d{2}\s*[ap]\.?m\.?)",
        r"(\d{1,2}[:.]\d{2}\s*[ap]\.?m\.?)\s+(?:Adjourned|Adjournment)",
    ]
    return _first_time(text, patterns)


def _first_time(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).replace(".", "").lower().strip()
    return None


def extract_staff_code(text: str) -> str | None:
    match = re.search(r"\b([A-Za-z]{2}/[A-Za-z]{2})\b", text)
    return match.group(1).upper() if match else None


def infer_meeting_type(filename: str, text: str, fallback: str | None = None) -> str:
    normalized_fallback = normalize_meeting_type(fallback) if fallback else None
    filename_blob = filename.lower()
    blob = f"{filename} {text[:1200]}".lower()
    if "cancel" in filename.lower() or "meeting cancelled" in blob:
        return "Cancelled Meeting"
    if normalized_fallback and (
        "pzdb" in filename_blob
        or "planning zoning" in filename_blob
        or "planning, zoning" in filename_blob
        or "village council" in normalized_fallback.lower()
        or "council" in normalized_fallback.lower()
    ):
        return normalized_fallback
    if "joint workshop" in blob:
        return "Joint Workshop"
    if "zoning hearing and comp plan workshop" in blob or "zoning hearing and comprehensive plan workshop" in blob:
        return "Combined Zoning Hearing / Workshop"
    if "organizational business meeting" in blob or "organizational meeting" in blob:
        return "Organizational Meeting"
    if "special emergency meeting" in blob:
        return "Special Emergency Meeting"
    if "special meeting budget hearing" in blob or "budget hearing" in blob or "millage" in blob:
        return "Budget Hearing"
    if "council special meeting" in blob or "special meeting" in blob:
        return "Special Meeting"
    if "comp plan workshop" in blob or "comprehensive plan workshop" in blob:
        return "Comprehensive Plan Workshop"
    if "planning zoning" in blob or "p&z" in blob or "pzdb" in blob:
        return "Planning Zoning & Design Board"
    if "public information" in blob or "open house" in blob:
        return "Public Information Meeting"
    if "zoning and dri development order hearing" in blob or "zoning hearing" in blob:
        return "Zoning Hearing"
    if "public hearing" in blob:
        return "Public Hearing"
    if "workshop" in blob:
        return "Workshop"
    if normalized_fallback:
        return normalized_fallback
    return "Village Council Regular Meeting"


def extract_agenda_entries(text: str) -> list[AgendaEntry]:
    if not text:
        return []

    entries: list[AgendaEntry] = []
    for match in re.finditer(
        r"\bAction:\s*(.*?)(?=\s*(?:Vote:|Motion:|Action:|Staff Presentation|Council Questions|Public Comment|Public Input|Board Communications|Adjourned|Adjournment|(?:\d{1,2}\.|[A-Z]\)|\([a-z0-9]\))\s+[A-Z]|$))",
        text,
        flags=re.I,
    ):
        action = _clean_action(match.group(1))
        if len(action) <= 8:
            continue
        vote_text = _extract_following_vote_text(text[match.end():])
        title = _infer_agenda_title(text[max(0, match.start() - 5000):match.start()])
        entries.append(AgendaEntry(title=title, action_text=action, vote_text=vote_text))

    if entries:
        return _dedupe_entries(entries)

    section_entries = _extract_agenda_section_entries(text)
    if section_entries:
        return _dedupe_entries(section_entries)

    fallback_patterns = [
        r"\b(Approved(?!\s+BY\s+(?:BOARD|COUNCIL))\s+.*?)(?=\s+(?:Motion:|Vote:|Action:|Public Comment|Adjourned|$))",
        r"\b(Adopted\s+.*?)(?=\s+(?:Motion:|Vote:|Action:|Public Comment|Adjourned|$))",
        r"\b(Passed\s+.*?)(?=\s+(?:Motion:|Vote:|Action:|Public Comment|Adjourned|$))",
    ]
    actions: list[str] = []
    for pattern in fallback_patterns:
        actions.extend(_clean_action(s) for s in re.findall(pattern, text, flags=re.I))
    return _dedupe_entries([AgendaEntry(title=None, action_text=a) for a in actions if len(a) > 12])


def extract_actions(text: str) -> list[str]:
    return [entry.action_text for entry in extract_agenda_entries(text)]


def split_csv_actions(action_taken: str | None) -> list[str]:
    if not action_taken:
        return []
    if action_taken in {"No action found", "No action extracted - verify PDF"}:
        return []
    return _dedupe([_clean_action(s) for s in action_taken.split("|") if len(_clean_action(s)) > 8])


def _clean_action(text: str) -> str:
    text = re.sub(
        r"\b(?:Village Council|Planning Zoning(?: & Design Board)?|Council Workshop|Special Meeting)"
        r".{0,80}?\s+Page\s+\d+\s+of\s+\d+\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"Vote\s*:\s*(?:\(.*?\))?\s*Aye\s*:?", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    return text


def _extract_following_vote_text(text: str) -> str | None:
    match = re.match(
        r"\s*Vote:\s*(.*?)(?=\s*(?:Motion:|Action:|Staff Presentation|Council Questions|Public Comment|Public Input|Board Communications|Adjourned|Adjournment|(?:\d{1,2}\.|[A-Z]\)|\([a-z0-9]\))\s+[A-Z]|$))",
        text,
        flags=re.I | re.S,
    )
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .;:")
    return value or None


def _extract_agenda_section_entries(text: str) -> list[AgendaEntry]:
    normalized = re.sub(r"\s+", " ", text)
    heading_pattern = re.compile(
        r"\b(?:PUBLIC INFORMATION MEETINGS?|PUBLIC HEARINGS?|WORKSHOP)\s+"
        r"(?:\([a-z]\)|\(\d+\)|[a-z]\)|\d+\.)\s+",
        flags=re.I,
    )
    stop_pattern = re.compile(
        r"\s+(?:PUBLIC INFORMATION MEETINGS?|PUBLIC HEARINGS?|WORKSHOP|PUBLIC INPUT|BOARD COMMUNICATIONS|"
        r"\d{1,2}\.\s+[A-Z][A-Z ]{2,})(?:\s+|\(|$)",
        flags=re.I,
    )
    entries: list[AgendaEntry] = []
    markers = list(heading_pattern.finditer(normalized))
    for index, marker in enumerate(markers):
        start = marker.end()
        next_start = markers[index + 1].start() if index + 1 < len(markers) else len(normalized)
        stop = stop_pattern.search(normalized, start, next_start)
        end = stop.start() if stop else next_start
        section = normalized[start:end].strip(" .;:")
        if not section or len(section) < 40:
            continue
        if not _section_has_project_signal(section):
            continue
        title = _clean_title(section)
        if not title:
            continue
        entries.append(AgendaEntry(title=title, action_text=f"No formal action recorded. {section[:900]}"))
    return entries


def _section_has_project_signal(section: str) -> bool:
    return bool(
        re.search(r"\b(?:DOS|LDO|DCI|COP|ADD|CPA|ZTA|DO)\s*\d{4}-[A-Z]?\d{3}\b", section, flags=re.I)
        or re.search(r"\b\d{3,6}\s+[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,5}\s+(?:Road|Rd|Street|St|Avenue|Ave|Parkway|Pkwy|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way|Terrace|Place|Pl)\b", section, flags=re.I)
    )


def _infer_agenda_title(context: str) -> str | None:
    context = re.sub(
        r"\b(?:Village Council|Planning Zoning(?: & Design Board)?|Council Workshop|Special Meeting)"
        r".{0,80}?\s+Page\s+\d+\s+of\s+\d+\b",
        " ",
        context,
        flags=re.I,
    )
    context = re.sub(r"\s+", " ", context).strip()
    if not context:
        return None
    last_motion = context.lower().rfind(" motion:")
    if last_motion >= 0:
        context = context[:last_motion].strip()

    marker_pattern = re.compile(
        r"(?:^|\s)(?:(?<!US\s)(?<!U\.S\.\s)(?:[1-9]|1\d|20)\.|[A-Z]\)|\([a-z]\)|\(\d+\))\s+",
        flags=re.I,
    )
    stop_pattern = re.compile(
        r"\s+(?:Motion:|Staff Presentation|Staff Comments|Council Questions|Council Comments|"
        r"Public Comment|Village Clerk|Village Manager|Questions or Comments|Action:|Vote:)",
        flags=re.I,
    )
    markers = list(marker_pattern.finditer(context))
    candidates: list[str] = []
    for index, match in enumerate(markers):
        start = match.end()
        next_marker_start = markers[index + 1].start() if index + 1 < len(markers) else len(context)
        end = next_marker_start
        stop = stop_pattern.search(context, start, next_marker_start)
        if stop:
            end = stop.start()
        title = _clean_title(context[start:end])
        if title and not _is_noise_title(title):
            candidates.append(title)
    return candidates[-1] if candidates else None


def _clean_title(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    text = re.sub(r"^(?:and\s+)?", "", text, flags=re.I).strip()
    if not text:
        return None
    return text[:255]


def _is_noise_title(title: str) -> bool:
    lo = title.lower()
    return lo in {
        "aye",
        "nay",
        "abstentions",
        "none",
    } or lo.startswith("final action agenda")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _dedupe_entries(values: list[AgendaEntry]) -> list[AgendaEntry]:
    seen: set[str] = set()
    out: list[AgendaEntry] = []
    for value in values:
        key = value.action_text.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def raw_pdf_url(pdf_path: str, repo: str = "EagleGIS-FGCU/EagleGIS", branch: str = "main") -> str:
    normalized = str(pdf_path or "").replace("\\", "/").strip("/")
    if "/" not in normalized:
        normalized = f"pdfs/{Path(normalized).name}"
    escaped = "/".join(quote(part) for part in normalized.split("/"))
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{escaped}"
