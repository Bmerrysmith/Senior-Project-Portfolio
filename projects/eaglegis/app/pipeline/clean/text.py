"""
Text-cleaning utilities targeting the artifacts produced by PDF
extraction of Village of Estero meeting minutes.

The bronze CSVs contain ``action_taken`` blobs that look like::

    "Approve d contract EC 2024- 06 with Florida Acquisition Services ...
     | Approve d Change Order No. 1 in the amount of $8,500.00 ... Village"

Common artifacts we need to clean:

  * intra-word splits caused by line breaks: ``Approve d`` -> ``Approved``,
    ``Ester o`` -> ``Estero``, ``A ccept ed`` -> ``Accepted``
  * de-hyphenated reference codes: ``2024- 06`` -> ``2024-06``
  * stray trailing tokens like ``Village`` appended to clauses
  * collapsed/duplicated whitespace, NBSPs, zero-width chars
  * smart quotes, em/en dashes, weird bullet glyphs
  * actions joined by ``|`` need to be split into a list

Keep this module pure: no I/O, no globals, only string in -> string/list out.
"""
from __future__ import annotations

import re
import unicodedata

ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff"}

# Hyphen-like Unicode characters that should collapse to ASCII '-'.
HYPHEN_VARIANTS = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign
}

# OCR splits a verb's tail across a line; some words are split at MULTIPLE
# points (e.g. "A ccept ed"). We list them explicitly so we never glue
# adjacent unrelated words by accident.
_SPLIT_VERB_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bA\s*ccept\s*ed\b"), "Accepted"),
    (re.compile(r"\bA\s*dopt\s*ed\b"), "Adopted"),
    (re.compile(r"\bA\s*pprove\s*d\b"), "Approved"),
    (re.compile(r"\bApprove\s+d\b"), "Approved"),
    (re.compile(r"\bAdopt\s+ed\b"), "Adopted"),
    (re.compile(r"\bAccept\s+ed\b"), "Accepted"),
    (re.compile(r"\bPass\s+ed\b"), "Passed"),
    (re.compile(r"\bDirect\s+ed\b"), "Directed"),
    (re.compile(r"\bAuthorize\s+d\b"), "Authorized"),
    (re.compile(r"\bReject\s+ed\b"), "Rejected"),
    (re.compile(r"\bContinue\s+d\b"), "Continued"),
    (re.compile(r"\bEndorse\s+d\b"), "Endorsed"),
    (re.compile(r"\bReceive\s+d\b"), "Received"),
    (re.compile(r"\bAward\s+ed\b"), "Awarded"),
    (re.compile(r"\bSchedule\s+d\b"), "Scheduled"),
    (re.compile(r"\bEster\s+o\b"), "Estero"),
    # "Merged" suffix: "Approve da perpetual" -> "Approved a perpetual".
    # The verb's tail letter got fused with the next word's first letter.
    (re.compile(r"\bApprove\s+d([a-z])\b"), r"Approved \1"),
    (re.compile(r"\bAdopt\s+ed([a-z])\b"), r"Adopted \1"),
    (re.compile(r"\bAccept\s+ed([a-z])\b"), r"Accepted \1"),
]

HYPHEN_GAP_RE = re.compile(r"(\d{4})-\s+(\d+)")
MULTI_WS_RE = re.compile(r"[ \t]+")
TRAILING_VILLAGE_RE = re.compile(r"\s+Village\.?\s*$")


def _strip_invisible(text: str) -> str:
    return "".join(ch for ch in text if ch not in ZERO_WIDTH)


def _normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for src, dst in HYPHEN_VARIANTS.items():
        text = text.replace(src, dst)
    return (
        text.replace("\u00a0", " ")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
    )


def _fix_split_verbs(text: str) -> str:
    """Glue back verbs split across lines: ``Approve d`` -> ``Approved``,
    ``A ccept ed`` -> ``Accepted``."""
    for pattern, replacement in _SPLIT_VERB_FIXES:
        text = pattern.sub(replacement, text)
    return text


def _fix_hyphen_gaps(text: str) -> str:
    """``2024- 06`` -> ``2024-06`` so reference codes stay searchable."""
    return HYPHEN_GAP_RE.sub(lambda m: f"{m.group(1)}-{m.group(2)}", text)


def _strip_trailing_village(clause: str) -> str:
    return TRAILING_VILLAGE_RE.sub("", clause).rstrip()


def clean_action_text(raw: str | None) -> str | None:
    """
    Normalize a raw ``action_taken`` blob.

    Returns ``None`` if the cleaned text is empty.
    """
    if raw is None:
        return None

    text = _strip_invisible(raw)
    text = _normalize_unicode(text)
    text = _fix_split_verbs(text)
    text = _fix_hyphen_gaps(text)
    text = MULTI_WS_RE.sub(" ", text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))

    text = text.strip()
    return text or None


def split_actions(raw: str | None) -> list[str]:
    """
    Break a cleaned action blob into a list of individual action clauses.

    Splits on the ``|`` separator used by the bronze data and drops the
    trailing ``Village`` artifact that frequently terminates clauses.
    Returns ``[]`` for empty/None input.
    """
    cleaned = clean_action_text(raw)
    if not cleaned:
        return []

    parts = [p.strip() for p in cleaned.split("|")]
    parts = [_strip_trailing_village(p) for p in parts if p]
    parts = [p for p in parts if p and p.lower() != "village"]
    return parts
