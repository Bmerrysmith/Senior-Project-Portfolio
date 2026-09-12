"""
Structured parsing of the ``action_taken`` blob into discrete action records.

The bronze/silver ``action_taken`` column is a ``|``-joined free-text blob of
council/board actions, e.g.::

    "Adopted Resolution No. 2017-02. | Approved Contract EC 2024-07 with ACME
     for $1,250,000 | Passed first reading ..."

:func:`split_actions` (in ``app/pipeline/clean/text.py``) already splits and
de-OCRs the blob into a list of cleaned clauses. This module classifies each
clause into a best-effort ``kind``, extracts a reference code (e.g.
``EC 2024-07``, ``2017-02``) and a dollar ``amount_usd`` when present.

Everything here is pure: string in -> dict/scalar out. No I/O, no globals.
The heuristics are intentionally conservative — see ``classify_kind`` and
``extract_amount_usd`` for accuracy caveats.
"""
from __future__ import annotations

import re

from app.pipeline.clean.text import split_actions

# Leading "verbs" that describe a council/board decision. Matched at the very
# start of a clause (case-insensitive), longest sensible canonical form wins.
_KIND_VERBS = [
    "Approved",
    "Adopted",
    "Accepted",
    "Authorized",
    "Awarded",
    "Passed",
    "Ratified",
    "Directed",
    "Continued",
    "Endorsed",
    "Received",
    "Rejected",
    "Denied",
    "Tabled",
    "Scheduled",
    "Confirmed",
]

# Noun categories. Order matters only for the regex alternation; selection picks
# the noun appearing earliest in the clause. Multi-word nouns listed first so
# "Change Order" is preferred over a later bare "Order"/"Contract".
_KIND_NOUNS = [
    "Change Order",
    "Task Authorization",
    "Resolution",
    "Ordinance",
    "Contract",
    "Agreement",
    "Payment",
    "Settlement",
    "Lease",
    "Easement",
    "Grant",
]

_VERB_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(v) for v in _KIND_VERBS) + r")\b",
    re.IGNORECASE,
)
_NOUN_RES = [
    (noun, re.compile(r"\b" + re.escape(noun) + r"\b", re.IGNORECASE))
    for noun in _KIND_NOUNS
]

# Reference codes: optional contract prefix (e.g. ``EC``) plus ``YYYY-NN`` such
# as ``EC 2024-07``, ``2017-02``, ``2022-83``. A bare 4-digit year followed by
# ``-`` and 1–4 digits. Dates like "February 5, 2025" never match (no dash).
_REF_CODE_RE = re.compile(r"\b([A-Z]{1,4}\s+)?(\d{4}-\d{1,4})\b")

# Dollar amounts: ``$30,000``, ``$8,500.00``, ``$1,250,000``, ``$1.2M``, ``$9.4k``.
_AMOUNT_RE = re.compile(
    r"\$\s*([0-9][0-9,]*(?:\.\d+)?)\s*([KkMmBb])?",
)
_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def classify_kind(clause: str | None) -> str:
    """Return a best-effort ``"<Verb> <Noun>"`` category for a clause.

    Falls back to just the verb (e.g. ``"Passed"``) when no noun category is
    found, and to ``"Other"`` when the clause doesn't start with a known verb.
    Heuristic — see module docstring.
    """
    if not clause:
        return "Other"
    vm = _VERB_RE.match(clause)
    if not vm:
        return "Other"
    verb = vm.group(1).capitalize()

    best_noun: str | None = None
    best_idx = len(clause) + 1
    for noun, rx in _NOUN_RES:
        m = rx.search(clause)
        if m and m.start() < best_idx:
            best_idx = m.start()
            best_noun = noun
    if best_noun:
        return f"{verb} {best_noun}"
    return verb


def extract_reference_code(clause: str | None) -> str | None:
    """Extract the first reference/ordinance/contract code, or ``None``.

    Examples: ``"EC 2024-07"``, ``"2017-02"``. Strips ``No.`` noise by keeping
    only the matched ``[PREFIX ]YYYY-NN`` token.
    """
    if not clause:
        return None
    m = _REF_CODE_RE.search(clause)
    if not m:
        return None
    prefix = (m.group(1) or "").strip()
    code = m.group(2)
    return f"{prefix} {code}".strip() if prefix else code


def extract_amount_usd(clause: str | None) -> float | None:
    """Parse the first dollar amount in a clause to a numeric USD value.

    Handles thousands separators and ``K``/``M``/``B`` suffixes
    (``"$1.2M"`` -> ``1200000.0``). Returns ``None`` when no amount is found.
    Heuristic: only the FIRST ``$`` amount is returned even if a clause lists
    several (e.g. a contract value plus a contingency).
    """
    if not clause:
        return None
    m = _AMOUNT_RE.search(clause)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    suffix = (m.group(2) or "").lower()
    if suffix in _MULTIPLIERS:
        value *= _MULTIPLIERS[suffix]
    return value


def parse_action_clause(clause: str) -> dict:
    """Turn a single cleaned clause into a structured dict (no ids)."""
    return {
        "kind": classify_kind(clause),
        "reference_code": extract_reference_code(clause),
        "amount_usd": extract_amount_usd(clause),
        "raw_text": clause,
    }


def parse_actions(blob: str | None) -> list[dict]:
    """Split + parse an ``action_taken`` blob into a list of structured dicts.

    Each dict has ``sequence`` (0-based), ``kind``, ``reference_code``,
    ``amount_usd``, ``raw_text``. Returns ``[]`` for empty/None input.
    """
    out: list[dict] = []
    for seq, clause in enumerate(split_actions(blob)):
        record = parse_action_clause(clause)
        record["sequence"] = seq
        out.append(record)
    return out
