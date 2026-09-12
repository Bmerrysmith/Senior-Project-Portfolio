"""
Classify agenda-item / ArcGIS rows by land-use category for filtering and ML.

Categories are inferred from project text (title, summary, action, application id).
"""
from __future__ import annotations

import re
from typing import Any

# Display order for filters / reports.
LAND_USE_CATEGORIES: tuple[str, ...] = (
    "residential",
    "commercial",
    "mixed_use",
    "industrial",
    "institutional",
    "infrastructure",
    "open_space",
    "administrative",
    "other",
)

# (category, patterns, weight) — higher weight = stronger signal.
_LAND_USE_RULES: tuple[tuple[str, tuple[str, ...], int], ...] = (
    (
        "mixed_use",
        (
            r"mixed.?use",
            r"live/work",
            r"retail and residential",
            r"residential and commercial",
        ),
        4,
    ),
    (
        "residential",
        (
            r"\bresidential\b",
            r"single.?family",
            r"multi.?family",
            r"\bapartment",
            r"\bcondo",
            r"\btownhome",
            r"\btownhouse",
            r"\bvilla\b",
            r"\bduplex",
            r"\bhousing",
            r"\b subdivision\b",
            r"\bplat\b",
            r"\blot \d",
            r"estero crossing residential",
            r"homeowners association",
            r"\bepd\b",
            r"estero preserve",
            r"cell tower.*residential",
        ),
        3,
    ),
    (
        "commercial",
        (
            r"\bcommercial\b",
            r"\bretail\b",
            r"\brestaurant\b",
            r"\bstore\b",
            r"\bwawa\b",
            r"\bgoodwill\b",
            r"\boffice\b",
            r"\bhotel\b",
            r"\bmotel\b",
            r"\bgas\b",
            r"convenience food",
            r"\bshopping\b",
            r"\bplaza\b",
            r"\bcpd\b",
            r"town center commercial",
            r"estero town commons",
            r"car wash",
            r"auto care",
            r"firestone",
            r"culver",
            r"ruby tuesday",
            r"lowes",
            r"marketplace at coconut",
        ),
        3,
    ),
    (
        "industrial",
        (
            r"\bindustrial\b",
            r"\bwarehouse\b",
            r"\bmanufactur",
            r"\bflex space\b",
        ),
        3,
    ),
    (
        "institutional",
        (
            r"\bschool\b",
            r"\bchurch\b",
            r"\bhospital\b",
            r"\blibrary\b",
            r"\bgovernment\b",
            r"\bmunicipal\b",
            r"fire rescue",
            r"public safety",
            r"community center",
        ),
        3,
    ),
    (
        "open_space",
        (
            r"\bpark\b",
            r"\brecreation\b",
            r"\btrail\b",
            r"\bpreserve\b",
            r"\bconservation\b",
            r"\bgreenway\b",
            r"\bopen space\b",
            r"landscap",
        ),
        2,
    ),
    (
        "infrastructure",
        (
            r"\broad\b",
            r"\butility\b",
            r"\bsewer\b",
            r"\bseptic\b",
            r"\bwater main\b",
            r"\bdrainage\b",
            r"\bsidewalk\b",
            r"\bbike\b",
            r"\bpedestrian\b",
            r"\beasement\b",
            r"right.?of.?way",
            r"\bsignal\b",
            r"traffic signal",
            r"street light",
            r"stormwater",
            r"demolition",
            r"structure demolition",
            r"monument sign",
            r"capital improvement",
            r"supplemental task authorization",
        ),
        2,
    ),
    (
        "administrative",
        (
            r"planning,? zoning",
            r"board member",
            r"reappoint",
            r"appointments",
            r"approve agenda",
            r"approved agenda",
            r"remote participation",
            r"millage rate",
            r"budget amendment",
            r"framework of cooperation",
            r"legislative delegation",
            r"credit card account",
        ),
        1,
    ),
)


def _row_text(row: dict[str, Any]) -> str:
    parts = [
        row.get("ProjectTitle"),
        row.get("ProjectName"),
        row.get("Summary"),
        row.get("ActionTaken"),
        row.get("Outcome"),
        row.get("MotionText"),
        row.get("ApplicationID"),
        row.get("ApplicantName"),
        row.get("Location"),
        row.get("LocationName"),
        row.get("AgendaItemType"),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def classify_land_use(row: dict[str, Any]) -> str:
    """Return the primary land-use category for an ArcGIS agenda-item row."""
    text = _row_text(row)
    if not text.strip():
        return "other"

    scores: dict[str, int] = {}
    for category, patterns, weight in _LAND_USE_RULES:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.I):
                scores[category] = scores.get(category, 0) + weight

    if not scores:
        return "other"

    # Drop weak administrative signal when a physical land-use category matched.
    if "administrative" in scores and len(scores) > 1:
        del scores["administrative"]

    best_score = max(scores.values())
    winners = [cat for cat, score in scores.items() if score == best_score]
    if len(winners) == 1:
        return winners[0]

    # Tie-break toward more specific physical use categories.
    priority = (
        "mixed_use",
        "commercial",
        "residential",
        "industrial",
        "institutional",
        "open_space",
        "infrastructure",
        "administrative",
        "other",
    )
    for cat in priority:
        if cat in winners:
            return cat
    return winners[0]
