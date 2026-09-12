"""
Collect canonical meeting-minute PDF URLs from estero-fl.gov.

Scrapes the Village Council and PZDB minutes index pages, extracts PDF
links, parses dates from filenames, and writes ``app/data/minutes_index.json``.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.pipeline import config

SOURCES = {
    "council": "https://estero-fl.gov/villagecouncilminutes/",
    "pzdb": "https://estero-fl.gov/pzdbminutes/",
}

PDF_RE = re.compile(
    r'href="(https://estero-fl\.gov/wp-content/uploads/library-ada/minutes/[^"]+\.pdf[^"]*)"',
    re.IGNORECASE,
)

DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mmddyyyy", re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")),
    ("iso", re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")),
    ("yyyymmdd", re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")),
    ("mmddyy", re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")),
)

MONTH_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

USER_AGENT = (
    "Mozilla/5.0 (compatible; EagleGIS-Minutes-Indexer/1.0; "
    "+https://github.com/EagleGIS-FGCU/EagleGIS)"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _safe_date(year: int, month: int, day: int) -> str | None:
    if not (2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def iso_date_from_filename(filename: str) -> str | None:
    low = filename.lower()
    if low.startswith("cancel") or "cancellation" in low or "rescheduled" in low:
        return None
    m = MONTH_RE.search(filename)
    if m:
        month = MONTHS[m.group(1).lower()]
        return _safe_date(int(m.group(3)), month, int(m.group(2)))
    for kind, pat in DATE_PATTERNS:
        m = pat.search(filename)
        if not m:
            continue
        if kind == "mmddyyyy":
            mm, dd, yyyy = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
            if iso:
                return iso
        elif kind == "iso":
            yyyy, mm, dd = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
            if iso:
                return iso
        elif kind == "yyyymmdd":
            yyyy, mm, dd = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
            if iso:
                return iso
        elif kind == "mmddyy":
            mm, dd, yy = m.groups()
            yyyy = 2000 + int(yy) if int(yy) < 50 else 1900 + int(yy)
            iso = _safe_date(yyyy, int(mm), int(dd))
            if iso:
                return iso
    return None


def extract_pdfs(html: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in PDF_RE.finditer(html):
        url = match.group(1)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def build_section(html: str) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    skipped: list[str] = []
    for url in extract_pdfs(html):
        filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        iso = iso_date_from_filename(filename)
        if not iso:
            skipped.append(filename)
            continue
        existing = mapping.get(iso)
        if existing is None:
            mapping[iso] = url
        else:
            score_new = sum(
                kw in filename.lower() for kw in ("approved", "final", "signed")
            )
            score_old = sum(
                kw in urllib.parse.unquote(existing).lower()
                for kw in ("approved", "final", "signed")
            )
            if score_new > score_old:
                mapping[iso] = url
    return mapping, skipped


def collect_minutes_index(out_path: Path | None = None) -> dict[str, Any]:
    """Scrape both index pages and return the manifest dict."""
    target = out_path or config.MINUTES_INDEX
    target.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "_meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_pages": SOURCES,
            "skipped": {},
        }
    }
    total = 0
    for key, url in SOURCES.items():
        html = fetch(url)
        mapping, skipped = build_section(html)
        result[key] = dict(sorted(mapping.items(), reverse=True))
        result["_meta"]["skipped"][key] = skipped
        total += len(mapping)

    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["_meta"]["total_entries"] = total
    result["_meta"]["path"] = str(target)
    return result


def load_minutes_index(path: Path | None = None) -> dict[str, Any]:
    """Load minutes_index.json if present; otherwise empty council/pzdb maps."""
    p = path or config.MINUTES_INDEX
    if not p.exists():
        return {"council": {}, "pzdb": {}, "_meta": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def minutes_body_key(type_name: str | None, type_id: int | None = None) -> str:
    """Return 'council' or 'pzdb' for minutes index lookup."""
    name = (type_name or "").lower()
    if type_id == 2 or "pzdb" in name or "planning" in name and "zoning" in name:
        return "pzdb"
    return "council"


def resolve_minutes_url(
    index: dict[str, Any],
    meeting_date: str,
    type_name: str | None = None,
    type_id: int | None = None,
) -> str | None:
    """Look up a canonical PDF URL by ISO date and meeting body."""
    if not meeting_date:
        return None
    iso = str(meeting_date)[:10]
    body = minutes_body_key(type_name, type_id)
    section = index.get(body) or {}
    return section.get(iso)
