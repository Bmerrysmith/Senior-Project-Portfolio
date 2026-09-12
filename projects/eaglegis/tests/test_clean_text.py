"""Unit tests for the action-text cleaner. Cases are pulled from real
ugly strings in app/data/meetings.csv."""
from app.pipeline.clean.text import clean_action_text, split_actions


def test_glues_split_verbs():
    raw = "Approve d contract EC 2024- 06 with Florida Acquisition Services"
    cleaned = clean_action_text(raw)
    assert "Approved contract EC 2024-06" in cleaned


def test_glues_accept_split():
    raw = "A ccept ed the Village's portion of the Opiod Settlement"
    cleaned = clean_action_text(raw)
    assert "Accepted" in cleaned
    assert "A ccept ed" not in cleaned


def test_normalizes_whitespace_and_smart_quotes():
    raw = "Adopted   Resolution\u00a0No.\u00a02016\u201101.\u200b"
    cleaned = clean_action_text(raw)
    assert cleaned == "Adopted Resolution No. 2016-01."


def test_returns_none_for_empty_input():
    assert clean_action_text(None) is None
    assert clean_action_text("") is None
    assert clean_action_text("   ") is None


def test_split_actions_drops_trailing_village():
    raw = (
        "Approved Resolution 2021-01. Village | "
        "Adopted Ordinance 2020-07."
    )
    parts = split_actions(raw)
    assert parts == [
        "Approved Resolution 2021-01.",
        "Adopted Ordinance 2020-07.",
    ]


def test_split_actions_handles_solo_village_token():
    raw = "Approved item one. | Village | Approved item two."
    parts = split_actions(raw)
    assert parts == ["Approved item one.", "Approved item two."]
