from __future__ import annotations

import re

from .config import CATEGORY_TERMS, LOCATION_SEEDS, PROJECT_ALIASES


VOTE_TERMS = [
    "motion", "seconded", "vote", "roll call", "aye", "nay",
    "approved", "adopted", "passed", "authorized", "continued",
]


def vote_detected(text: str) -> bool:
    lo = text.lower()
    return any(term in lo for term in VOTE_TERMS)


def infer_action_type(text: str, meeting_type: str) -> str:
    lo = text.lower()
    if "meeting cancelled" in lo or "cancelled" in lo:
        return "No Action"
    if any(term in lo for term in [
        "approve agenda", "approved agenda", "agenda as amended",
        "remote participation", "participate remotely", "excused",
    ]):
        return "Administrative"
    if "consent agenda" in lo:
        return "Consent Agenda"
    if "ordinance" in lo or "first reading" in lo or "second reading" in lo:
        return "Ordinance"
    if "resolution" in lo:
        return "Resolution"
    if any(term in lo for term in ["contract", "task authorization", "change order", "agreement"]):
        return "Contract Approval"
    if any(term in lo for term in ["budget", "millage", "capital improvement"]):
        return "Budget"
    if "public comment" in lo:
        return "Public Comment"
    if "presentation" in lo:
        return "Presentation"
    if "workshop" in meeting_type.lower() or any(term in lo for term in ["discussion", "consensus", "direction"]):
        return "Discussion"
    if vote_detected(text):
        return "Vote"
    return "Unknown"


def infer_category(text: str, action_type: str) -> str:
    lo = text.lower()
    for category, terms in CATEGORY_TERMS.items():
        if any(term in lo for term in terms):
            return category
    return action_type if action_type != "Unknown" else "Uncategorized"


def match_projects(text: str, fallback_project: str | None = None) -> list[str]:
    lo = text.lower()
    matches = [
        project for project, aliases in PROJECT_ALIASES.items()
        if any(re.search(rf"\b{re.escape(alias)}\b", lo) for alias in aliases)
    ]
    if fallback_project and fallback_project not in matches:
        matches.append(fallback_project)
    return matches


def match_locations(text: str, fallback_location: str | None = None) -> list[str]:
    lo = text.lower()
    matches = []
    for name, data in LOCATION_SEEDS.items():
        aliases = [name, *(data.get("aliases") or [])]
        if any(re.search(rf"\b{re.escape(alias.lower())}\b", lo) for alias in aliases):
            matches.append(name)
    if fallback_location and fallback_location not in matches:
        matches.append(fallback_location)
    return matches


def extract_address_candidates(text: str) -> list[str]:
    """Find address-like references suitable for geocoding review."""
    suffixes = (
        "Road", "Rd", "Street", "St", "Avenue", "Ave", "Parkway", "Pkwy",
        "Boulevard", "Blvd", "Lane", "Ln", "Drive", "Dr", "Court", "Ct",
        "Circle", "Cir", "Way", "Terrace", "Place", "Pl", "Trail", "Trl",
        "Highway", "Hwy",
    )
    suffix_pattern = "|".join(suffixes)
    token = r"(?:[A-Z][A-Za-z.'-]*|[A-Z]{1,4}|[0-9]+(?:st|nd|rd|th)?)"
    patterns = [
        rf"\b\d{{3,6}}\s+(?:{token}\s+){{0,5}}(?:{suffix_pattern})\b",
        rf"\b\d{{3,5}}\s+Block\s+(?:{token}\s+){{0,5}}(?:{suffix_pattern})\b",
    ]
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            value = re.sub(r"\s+", " ", match.group(0)).strip(" .,;")
            if not _looks_like_address(value):
                continue
            if value.lower() not in {c.lower() for c in candidates}:
                candidates.append(value)
    return candidates


def _looks_like_address(value: str) -> bool:
    lo = value.lower()
    bad_fragments = [
        "contract", "engineering", "services", "construction", "budget",
        "workshop", "minutes", "agenda", "meeting", "action", "amendment",
        "acceptance", "provide", "proposed", "replace", "repair",
    ]
    if any(fragment in lo for fragment in bad_fragments):
        return False
    first = re.match(r"\d+", value)
    if first and int(first.group(0)) == 0:
        return False
    return True


def needs_review(
    *,
    needs_ocr: bool,
    date_missing: bool,
    action_count: int,
    project_count: int,
    location_count: int,
    used_csv_fallback: bool,
) -> bool:
    return (
        needs_ocr
        or date_missing
        or action_count == 0
        or project_count == 0
        or location_count == 0
        or used_csv_fallback
    )
