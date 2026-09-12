"""
Tests for structured meeting-action parsing (``app/pipeline/clean/actions.py``)
and the silver ``meeting_actions.csv`` artifact.

Unit tests pin the kind / reference-code / amount heuristics; the e2e test
runs the real ``build_silver()`` and asserts referential integrity against the
silver meetings table.
"""
from __future__ import annotations

import csv

from app.pipeline import config
from app.pipeline.clean.actions import (
    classify_kind,
    extract_amount_usd,
    extract_reference_code,
    parse_actions,
)
from app.pipeline.load.silver import build_meeting_actions, build_silver


def _read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# classify_kind
# ---------------------------------------------------------------------------

def test_classify_kind_verb_plus_noun():
    assert classify_kind("Adopted Resolution No. 2017-02.") == "Adopted Resolution"
    assert classify_kind("Approved Contract EC 2024-07 with ACME") == "Approved Contract"
    assert classify_kind("Approved Change Order No. 1 in the amount of $8,500") == "Approved Change Order"
    assert classify_kind("Accepted a payment of $30,000 from ProEnergy") == "Accepted Payment"


def test_classify_kind_verb_only_and_other():
    assert classify_kind("Passed first reading and set second reading") == "Passed"
    assert classify_kind("Directed Village Land Use Attorney to investigate") == "Directed"
    assert classify_kind("No action required. 8.") == "Other"
    assert classify_kind("") == "Other"
    assert classify_kind(None) == "Other"


def test_classify_kind_picks_earliest_noun():
    # "Change Order" precedes "Contract" in the clause -> Change Order wins.
    clause = "Approved Change Order No. 1 to Contract EC 2022-83 for sewer testing"
    assert classify_kind(clause) == "Approved Change Order"


# ---------------------------------------------------------------------------
# extract_reference_code
# ---------------------------------------------------------------------------

def test_extract_reference_code_variants():
    assert extract_reference_code("Approved Contract EC 2024-07 with ACME") == "EC 2024-07"
    assert extract_reference_code("Adopted Resolution No. 2017-02.") == "2017-02"
    assert extract_reference_code("adopted Ordinance No. 2016-15.") == "2016-15"


def test_extract_reference_code_none_when_absent():
    assert extract_reference_code("Adopted the Information Security Policy.") is None
    # A plain date must not be mistaken for a code (no dash between numbers).
    assert extract_reference_code("Continued to January 20, 2016.") is None
    assert extract_reference_code(None) is None


# ---------------------------------------------------------------------------
# extract_amount_usd
# ---------------------------------------------------------------------------

def test_extract_amount_usd_formats():
    assert extract_amount_usd("payment of $30,000 from ProEnergy") == 30000.0
    assert extract_amount_usd("Change Order No. 1 in the amount of $8,500.00") == 8500.0
    assert extract_amount_usd("for $1,250,000") == 1250000.0
    assert extract_amount_usd("estimated $1.2M total") == 1200000.0
    assert extract_amount_usd("about $9.4k") == 9400.0


def test_extract_amount_usd_first_match_and_none():
    # Only the first amount is returned even if several appear.
    assert extract_amount_usd("$249,480, approve a $25,000 contingency") == 249480.0
    assert extract_amount_usd("No dollars mentioned here") is None
    assert extract_amount_usd(None) is None


# ---------------------------------------------------------------------------
# parse_actions / build_meeting_actions
# ---------------------------------------------------------------------------

def test_parse_actions_assigns_sequence():
    blob = "Adopted Resolution No. 2017-02. | Approved Contract EC 2024-07 for $1,250,000"
    parsed = parse_actions(blob)
    assert [p["sequence"] for p in parsed] == [0, 1]
    assert parsed[0]["kind"] == "Adopted Resolution"
    assert parsed[1]["reference_code"] == "EC 2024-07"
    assert parsed[1]["amount_usd"] == 1250000.0


def test_build_meeting_actions_stable_ids():
    meetings = [
        {"meeting_id": 10, "action_taken": "Adopted Resolution No. 2017-02. | Passed first reading"},
        {"meeting_id": 11, "action_taken": "Approved Contract EC 2024-07 for $1,250,000"},
        {"meeting_id": 12, "action_taken": None},
    ]
    rows = build_meeting_actions(meetings)
    assert [r["action_id"] for r in rows] == [1, 2, 3]
    assert [r["meeting_id"] for r in rows] == [10, 10, 11]
    assert [r["sequence"] for r in rows] == [0, 1, 0]


# ---------------------------------------------------------------------------
# End-to-end against the real bronze/silver data
# ---------------------------------------------------------------------------

def test_build_silver_emits_meeting_actions_with_valid_fks():
    report = build_silver()

    assert "meeting_actions" in report
    assert report["meeting_actions"]["out"] >= 1
    assert config.SILVER_MEETING_ACTIONS.exists()

    meetings = _read_csv(config.SILVER_MEETINGS)
    actions = _read_csv(config.SILVER_MEETING_ACTIONS)

    assert len(actions) == report["meeting_actions"]["out"]

    meeting_ids = {m["meeting_id"] for m in meetings}
    assert all(a["meeting_id"] in meeting_ids for a in actions)

    # action_id is a dense, stable 1..N sequence.
    ids = [int(a["action_id"]) for a in actions]
    assert ids == list(range(1, len(actions) + 1))

    # Every action carries a kind and a raw_text.
    assert all(a["kind"] for a in actions)
    assert all(a["raw_text"] for a in actions)
