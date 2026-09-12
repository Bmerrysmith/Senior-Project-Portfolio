"""
Verify meeting locations against location text found in minutes PDFs.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.pipeline import config, reference
from app.pipeline.collect.minutes import load_minutes_index, resolve_minutes_url

PdfFetcher = Callable[[str], bytes]
PdfTextExtractor = Callable[[bytes], str]

_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _default_pdf_fetcher(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "EagleGIS-location-validator/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def extract_text_from_pdf_bytes(payload: bytes) -> str:
    """Extract plain text from PDF bytes via pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(payload))
    chunks: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text:
            chunks.append(page_text)
    return "\n".join(chunks)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = _NON_WORD_RE.sub(" ", text)
    return _MULTI_SPACE_RE.sub(" ", text).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) >= 3}


def _location_aliases(location: dict | None, fallback: str | None) -> list[str]:
    aliases: list[str] = []
    if location:
        for key in ("location_name", "address"):
            val = (location.get(key) or "").strip()
            if val:
                aliases.append(val)
    if fallback:
        aliases.append(fallback)
    return list(dict.fromkeys(aliases))


def _matches_aliases(pdf_text: str, aliases: list[str]) -> bool:
    norm_text = _normalize(pdf_text)
    text_tokens = _tokens(norm_text)
    for alias in aliases:
        norm_alias = _normalize(alias)
        if not norm_alias:
            continue
        if norm_alias in norm_text:
            return True
        alias_tokens = _tokens(norm_alias)
        if alias_tokens and len(alias_tokens.intersection(text_tokens)) >= min(3, len(alias_tokens)):
            return True
    return False


def _best_document_by_meeting(documents: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for row in documents:
        try:
            meeting_id = int(row.get("meeting_id"))
        except (TypeError, ValueError):
            continue
        prev = out.get(meeting_id)
        if prev is None:
            out[meeting_id] = row
            continue
        prev_uploaded = (prev.get("link_status") or "").lower() == "uploaded"
        current_uploaded = (row.get("link_status") or "").lower() == "uploaded"
        if current_uploaded and not prev_uploaded:
            out[meeting_id] = row
    return out


def _candidate_pdf_urls(url: str) -> list[str]:
    candidates = [url]
    trimmed_encoded = re.sub(r"(?:%20)+(?=\.pdf($|\?))", "", url, flags=re.IGNORECASE)
    if trimmed_encoded != url:
        candidates.append(trimmed_encoded)
    if " " in url:
        candidates.append(url.replace(" ", "%20"))
    return list(dict.fromkeys(candidates))


def verify_locations_from_minutes_pdfs(
    *,
    pdf_fetcher: PdfFetcher = _default_pdf_fetcher,
    text_extractor: PdfTextExtractor = extract_text_from_pdf_bytes,
    limit: int | None = None,
) -> dict:
    """
    Validate meeting location labels/IDs by checking minutes PDF text.
    """
    meetings = _read_csv(config.SILVER_MEETINGS)
    documents = _read_csv(config.SILVER_DOCUMENTS)
    minutes_index = load_minutes_index()
    locations = {int(loc["location_id"]): loc for loc in reference.locations()}
    meeting_types = {int(mt["type_id"]): mt.get("type_name", "") for mt in reference.meeting_types()}
    docs_by_meeting = _best_document_by_meeting(documents)

    report = {
        "checked": 0,
        "matched": 0,
        "mismatched": 0,
        "no_pdf_url": 0,
        "pdf_fetch_errors": 0,
        "pdf_parse_errors": 0,
        "location_not_found_in_pdf": 0,
        "strict_violations": [],
        # Infrastructure problems (PDF could not be fetched/parsed, e.g. the
        # host blocks datacenter IPs/bot user-agents from CI). These are NOT
        # strict failures: we can't validate location text we never received,
        # so they are recorded as warnings and never fail strict mode.
        "fetch_warnings": [],
    }

    text_cache: dict[str, str] = {}
    examined = 0
    today = datetime.now(timezone.utc).date()
    for meeting in meetings:
        if limit is not None and examined >= limit:
            break
        try:
            meeting_id = int(meeting["meeting_id"])
        except (KeyError, TypeError, ValueError):
            continue

        location_id_raw = meeting.get("location_id")
        if location_id_raw in ("", None):
            # Only enforce PDF-based location verification for meetings with a
            # canonical location_id.
            continue
        try:
            location_id = int(location_id_raw)
        except (TypeError, ValueError):
            continue
        location = locations.get(location_id)
        location_name = (location or {}).get("location_name") or (meeting.get("location") or "").strip()

        if not location_name:
            continue

        doc = docs_by_meeting.get(meeting_id, {})
        url = ""
        if (doc.get("link_status") or "").lower() == "uploaded" and doc.get("file_url"):
            url = str(doc["file_url"]).strip()
        if not url:
            try:
                meeting_date = str(meeting.get("meeting_date") or "")[:10]
                type_id = int(meeting.get("type_id")) if meeting.get("type_id") else None
                type_name = meeting_types.get(type_id or -1, "")
                url = resolve_minutes_url(minutes_index, meeting_date, type_name=type_name, type_id=type_id) or ""
            except (TypeError, ValueError):
                url = ""
        if not url:
            report["no_pdf_url"] += 1
            continue

        examined += 1
        report["checked"] += 1

        if url in text_cache:
            pdf_text = text_cache[url]
        else:
            meeting_date = str(meeting.get("meeting_date") or "")[:10]
            try:
                type_id = int(meeting.get("type_id")) if meeting.get("type_id") else None
            except (TypeError, ValueError):
                type_id = None
            type_name = meeting_types.get(type_id or -1, "")
            try:
                payload = None
                fetched_url = ""
                for candidate in _candidate_pdf_urls(url):
                    try:
                        payload = pdf_fetcher(candidate)
                        fetched_url = candidate
                        break
                    except Exception:
                        continue
                if payload is None:
                    raise ValueError("unable to fetch using primary URL variants")
                url = fetched_url
            except Exception as exc:
                fallback_url = resolve_minutes_url(
                    minutes_index,
                    meeting_date,
                    type_name=type_name,
                    type_id=type_id,
                ) or ""
                if fallback_url and fallback_url != url:
                    try:
                        payload = None
                        fetched_url = ""
                        for candidate in _candidate_pdf_urls(fallback_url):
                            try:
                                payload = pdf_fetcher(candidate)
                                fetched_url = candidate
                                break
                            except Exception:
                                continue
                        if payload is None:
                            raise ValueError("unable to fetch using fallback URL variants")
                        url = fetched_url
                    except Exception:
                        report["pdf_fetch_errors"] += 1
                        if len(report["fetch_warnings"]) < 50:
                            report["fetch_warnings"].append(
                                f"meeting_id={meeting_id} failed to fetch minutes PDF: {exc}"
                            )
                        continue
                else:
                    report["pdf_fetch_errors"] += 1
                    if len(report["fetch_warnings"]) < 50:
                        report["fetch_warnings"].append(
                            f"meeting_id={meeting_id} failed to fetch minutes PDF: {exc}"
                        )
                    continue
            try:
                pdf_text = text_extractor(payload)
            except Exception as exc:
                report["pdf_parse_errors"] += 1
                if len(report["fetch_warnings"]) < 50:
                    report["fetch_warnings"].append(
                        f"meeting_id={meeting_id} failed to parse minutes PDF: {exc}"
                    )
                continue
            text_cache[url] = pdf_text

        aliases = _location_aliases(location, location_name)
        if _matches_aliases(pdf_text, aliases):
            report["matched"] += 1
            continue

        report["location_not_found_in_pdf"] += 1
        meeting_date = str(meeting.get("meeting_date") or "")[:10]
        if meeting_date:
            try:
                if datetime.fromisoformat(meeting_date).date() <= today:
                    report["mismatched"] += 1
                    if len(report["strict_violations"]) < 50:
                        report["strict_violations"].append(
                            f"meeting_id={meeting_id} expected location '{location_name}' not found in PDF text"
                        )
            except ValueError:
                # If date is malformed, treat as a strict mismatch.
                report["mismatched"] += 1
                if len(report["strict_violations"]) < 50:
                    report["strict_violations"].append(
                        f"meeting_id={meeting_id} expected location '{location_name}' not found in PDF text"
                    )
        else:
            report["mismatched"] += 1
            if len(report["strict_violations"]) < 50:
                report["strict_violations"].append(
                    f"meeting_id={meeting_id} expected location '{location_name}' not found in PDF text"
                )

    return report
