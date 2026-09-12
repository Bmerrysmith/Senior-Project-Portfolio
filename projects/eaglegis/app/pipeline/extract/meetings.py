"""
Discover newly-held Village of Estero meetings and propose them for review.

The bronze inputs ``app/data/meetings.csv`` (Village Council, ``type_id=1``) and
``app/data/documents.csv`` (Planning, Zoning & Design Board, ``type_id=2``) are
hand-maintained.  This extractor scrapes estero-fl.gov, derives the set of
meeting dates that *appear on the site* but are *not yet in bronze*, and writes
them to a CANDIDATE file (``app/data/extract/candidate_meetings.csv``) for a
human to review.  It NEVER edits bronze.

Design mirrors ``app/pipeline/collect/minutes.py``: stdlib ``urllib`` only, a
``USER_AGENT``, defensive parsing, pure (offline-testable) helper functions, and
a ``fetch(url)`` seam so tests never hit the network.

----------------------------------------------------------------------------
LIVE-SELECTOR CAVEAT (read before tuning):
The Village's *agenda/calendar* surface (``estero-fl.gov/meetings`` ->
``estero-fl.gov/agendas``) is a JavaScript single-page app served by ChampDS
(``play.champds.com/esterofl/...``).  Its meeting list is NOT present in the
server-rendered HTML, so it cannot be scraped with the stdlib alone.

The reliable, stdlib-scrapeable discovery surface is therefore the two *minutes*
index pages, which expose dated meeting-minute PDF links as soon as minutes are
posted.  A dated PDF that is absent from bronze is, by definition, a meeting we
have not catalogued yet -- exactly the signal we want.  ``SOURCES`` and
``LINK_RE`` are configurable, so if/when a static (server-rendered) agenda or
calendar index becomes available it can be added here without code changes
elsewhere.  Live selectors may need future tuning; the pure parsing functions
below are pinned by offline tests regardless.
----------------------------------------------------------------------------
"""
from __future__ import annotations

import csv
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.pipeline import config  # READ-ONLY: only paths are read, never written

# Discovery source pages, keyed by canonical body.  These are the same minutes
# index pages the minutes collector uses; they are the only estero-fl.gov
# surface that lists dated meetings in server-rendered HTML (see module docstring).
SOURCES: dict[str, str] = {
    "council": "https://estero-fl.gov/villagecouncilminutes/",
    "pzdb": "https://estero-fl.gov/pzdbminutes/",
}

# Canonical body -> bronze type_id.
BODY_TYPE_ID: dict[str, int] = {"council": 1, "pzdb": 2}

# Default link selector: meeting-minute PDFs under the library-ada path.  Made
# configurable so an agenda/calendar index (different path) can be slotted in.
LINK_RE = re.compile(
    r'href="(https://estero-fl\.gov/wp-content/uploads/[^"]*?/minutes/[^"]+\.pdf[^"]*)"',
    re.IGNORECASE,
)

# Any anchor (used when discovering from a page whose dates live in link text
# rather than in the file path, e.g. a future static agenda index).
ANCHOR_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")

DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mmddyyyy", re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")),
    ("iso", re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")),
    ("slash", re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")),
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

# Link/text fragments that indicate a non-meeting (skip when discovering).
SKIP_TOKENS = ("cancel", "cancellation", "rescheduled", "notice")

USER_AGENT = (
    "Mozilla/5.0 (compatible; EagleGIS-Meetings-Discovery/1.0; "
    "+https://github.com/EagleGIS-FGCU/EagleGIS)"
)


def fetch(url: str) -> str:
    """Network seam -- patched out in tests so nothing here hits the network."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Pure helpers (no I/O, no network) -- pinned by tests/test_extract_meetings.py
# --------------------------------------------------------------------------- #
def _safe_date(year: int, month: int, day: int) -> str | None:
    if not (2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def parse_meeting_date(text: str) -> str | None:
    """Parse a meeting date out of arbitrary text (filename or link label).

    Returns an ISO ``YYYY-MM-DD`` string or ``None`` if no plausible meeting
    date is found.  Cancellation / rescheduling notices are intentionally
    skipped so they never propose a candidate meeting.
    """
    if not text:
        return None
    low = text.lower()
    if any(tok in low for tok in SKIP_TOKENS):
        return None
    m = MONTH_RE.search(text)
    if m:
        iso = _safe_date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        if iso:
            return iso
    for kind, pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if kind == "mmddyyyy":
            mm, dd, yyyy = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
        elif kind in ("iso", "yyyymmdd"):
            yyyy, mm, dd = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
        elif kind == "slash":
            mm, dd, yyyy = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
        else:  # mmddyy
            mm, dd, yy = m.groups()
            yyyy = 2000 + int(yy) if int(yy) < 50 else 1900 + int(yy)
            iso = _safe_date(yyyy, int(mm), int(dd))
        if iso:
            return iso
    return None


def normalize_iso(value: Any) -> str | None:
    """Normalize a date-ish value (ISO, datetime string, slashes, month name,
    or compact ``MMDDYYYY``) to ``YYYY-MM-DD``; return ``None`` if not a date."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "nan"):
        return None
    # Fast path: leading ISO date (handles "2025-01-02" and "2025-01-02T09:30").
    head = s[:10]
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", head)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return parse_meeting_date(s)


def normalize_body(value: Any) -> str | None:
    """Map a type_id / type_name / body label to canonical 'council' or 'pzdb'."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in ("1", "council", "village council"):
        return "council"
    if s in ("2", "pzdb"):
        return "pzdb"
    if "pzdb" in s or ("planning" in s and "zoning" in s):
        return "pzdb"
    if "council" in s:
        return "council"
    return None


def iter_anchors(html: str) -> list[tuple[str, str]]:
    """Return ``(href, visible_text)`` pairs for every ``<a>`` in the HTML."""
    out: list[tuple[str, str]] = []
    for m in ANCHOR_RE.finditer(html):
        href = m.group(1)
        text = TAG_RE.sub("", m.group(2))
        text = re.sub(r"\s+", " ", text).strip()
        out.append((href, text))
    return out


def extract_links(html: str, link_re: re.Pattern[str] = LINK_RE) -> list[str]:
    """Return de-duplicated links matching ``link_re`` (order preserved)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in link_re.finditer(html):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def discover_meetings(
    html: str,
    body: str,
    *,
    link_re: re.Pattern[str] = LINK_RE,
) -> tuple[list[dict[str, str]], list[str]]:
    """Discover ``(body, ISO date)`` candidates from a page's HTML.

    Strategy (defensive, two complementary passes):
      1. ``link_re`` matches -> parse a date from the file name (current path
         on estero-fl.gov; dates live in the PDF filename).
      2. Fallback: scan every anchor and parse a date from its visible text
         (covers a future static agenda index where dates are link labels).

    Returns ``(candidates, skipped)`` where each candidate is a dict with
    ``body``, ``meeting_date`` (ISO), ``source_url`` and ``source_filename``;
    ``skipped`` lists link names that looked relevant but had no parseable date.
    Candidates are de-duplicated per (body, date).
    """
    by_date: dict[str, dict[str, str]] = {}
    skipped: list[str] = []

    for url in extract_links(html, link_re):
        filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        iso = parse_meeting_date(filename)
        if not iso:
            skipped.append(filename)
            continue
        by_date.setdefault(
            iso,
            {
                "body": body,
                "meeting_date": iso,
                "source_url": url,
                "source_filename": filename,
            },
        )

    # Fallback pass over anchor text only if the link selector found nothing,
    # so we do not spam candidates from unrelated dated links on busy pages.
    if not by_date:
        for href, text in iter_anchors(html):
            iso = parse_meeting_date(text) or parse_meeting_date(
                urllib.parse.unquote(href.rsplit("/", 1)[-1])
            )
            if not iso:
                continue
            by_date.setdefault(
                iso,
                {
                    "body": body,
                    "meeting_date": iso,
                    "source_url": href,
                    "source_filename": text or href,
                },
            )

    candidates = [by_date[d] for d in sorted(by_date)]
    return candidates, skipped


def diff_against_bronze(
    discovered: Iterable[dict[str, Any]],
    bronze_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only discovered meetings whose ``(body, ISO date)`` is NOT in bronze.

    Both inputs are iterables of dicts.  ``body`` may be given as a canonical
    label, a ``type_id``, or a ``type_name`` (``normalize_body`` handles each);
    the date may be any value ``normalize_iso`` understands.  Discovered rows
    are de-duplicated on ``(body, date)`` and rows that cannot be normalized are
    dropped (they are not safe to propose).
    """
    def key(row: dict[str, Any]) -> tuple[str, str] | None:
        body = normalize_body(
            row.get("body")
            if row.get("body") is not None
            else row.get("type_id", row.get("type_name"))
        )
        iso = normalize_iso(row.get("meeting_date", row.get("doc_date")))
        if body is None or iso is None:
            return None
        return (body, iso)

    bronze_keys = {k for k in (key(r) for r in bronze_rows) if k is not None}

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in discovered:
        k = key(row)
        if k is None or k in bronze_keys or k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# I/O wrappers
# --------------------------------------------------------------------------- #
EXTRACT_DIR = config.EXTRACT_DIR
CANDIDATE_MEETINGS = config.CANDIDATE_MEETINGS

CANDIDATE_FIELDS = [
    "body",
    "type_id",
    "meeting_date",
    "meeting_year",
    "source_url",
    "source_filename",
    "discovered_utc",
    "note",
]


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_bronze_rows(
    meetings_path: Path | None = None,
    documents_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Read bronze meetings + documents into normalized ``{body, meeting_date}``
    rows (READ-ONLY).  Defaults to the bronze paths declared in ``config``."""
    rows: list[dict[str, Any]] = []
    for r in _read_rows(meetings_path or config.BRONZE_MEETINGS):
        rows.append({"body": normalize_body(r.get("type_id")), "meeting_date": r.get("meeting_date")})
    for r in _read_rows(documents_path or config.BRONZE_DOCUMENTS):
        body = normalize_body(r.get("type_name")) or normalize_body(r.get("type_id"))
        rows.append({"body": body, "meeting_date": r.get("meeting_date")})
    return rows


def collect_candidate_meetings(out_path: Path | None = None) -> dict[str, Any]:
    """Scrape both bodies, diff against current bronze, and write candidates.

    Writes ``app/data/extract/candidate_meetings.csv`` (never bronze) and
    returns a small report dict (counts, skipped, path).
    """
    target = out_path or CANDIDATE_MEETINGS
    target.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bronze_rows = read_bronze_rows()

    discovered: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "generated": now,
        "sources": dict(SOURCES),
        "discovered": {},
        "skipped": {},
        "errors": {},
    }

    for body, url in SOURCES.items():
        try:
            html = fetch(url)
        except Exception as exc:  # network/HTML issues must not crash the run
            report["errors"][body] = f"{type(exc).__name__}: {exc}"
            report["discovered"][body] = 0
            report["skipped"][body] = []
            continue
        candidates, skipped = discover_meetings(html, body)
        report["discovered"][body] = len(candidates)
        report["skipped"][body] = skipped
        discovered.extend(candidates)

    new_candidates = diff_against_bronze(discovered, bronze_rows)

    for cand in new_candidates:
        iso = cand["meeting_date"]
        cand.setdefault("type_id", BODY_TYPE_ID.get(cand["body"], ""))
        cand.setdefault("meeting_year", iso[:4] if iso else "")
        cand.setdefault("discovered_utc", now)
        cand.setdefault("note", "auto-discovered; review before adding to bronze")

    new_candidates.sort(key=lambda c: (c["body"], c["meeting_date"]))

    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        for cand in new_candidates:
            writer.writerow({k: cand.get(k, "") for k in CANDIDATE_FIELDS})

    report["total_discovered"] = len(discovered)
    report["total_new"] = len(new_candidates)
    report["bronze_known"] = len(
        {
            k
            for k in (
                (normalize_body(r.get("body")), normalize_iso(r.get("meeting_date")))
                for r in bronze_rows
            )
            if None not in k
        }
    )
    report["path"] = str(target)
    return report
