"""
Tests for the AI gold layer (``app/pipeline/publish/ai_gold.py``).

These records are agenda-item grain with provenance and confidence metadata so
LLM/RAG pipelines can ground answers and skip low-trust rows.
"""
from __future__ import annotations

import csv
import json

from app.pipeline import config
from app.pipeline.load.silver import build_silver
from app.pipeline.publish.ai_gold import (
    AI_GOLD_FIELDS,
    SourceEnrichment,
    _application_type,
    _extraction_confidence,
    _is_weak_text,
    _load_source_enrichment,
    _transform_arcgis_row,
    build_ai_gold,
)
from app.pipeline.publish.gold import build_gold


def test_is_weak_text_flags_placeholders():
    assert _is_weak_text("See minutes")
    assert _is_weak_text("")
    assert not _is_weak_text("Approved Development Order with staff conditions")


def test_application_type_maps_prefixes():
    assert _application_type("DOS2023-E005") == "development_order"
    assert _application_type("O2024-03") == "ordinance"


def test_extraction_confidence_high_when_grounded():
    assert _extraction_confidence(
        review_required=False,
        action_text="Approved the application with staff conditions",
        outcome_text="Approved",
        motion_text="",
        summary_text="Development order for parcel",
        address="10081 Estero Town Commons Place",
        geocode_conf=1.0,
    ) == "high"


def test_transform_preserves_distinct_action_and_summary():
    enrichment = SourceEnrichment()
    row = _transform_arcgis_row(
        {
            "Board": "Village Council",
            "AgendaItemID": "1007",
            "MeetingDate": "2024-04-03",
            "MeetingYear": "2024",
            "MeetingType": "Regular Council Meeting",
            "AgendaItemNumber": "10",
            "AgendaItemType": "Ordinance",
            "ProjectTitle": "Ordinance No. 2024-05",
            "Summary": "Long descriptive summary of the ordinance item",
            "ActionTaken": "Passed first reading of Ordinance No. 2024-05",
            "Outcome": "Passed first reading",
            "MotionText": "Motion to pass first reading",
            "Location": "123 Main St, Estero, FL",
            "Latitude": "26.43",
            "Longitude": "-81.78",
            "GeocodeConfidence": "0.5",
            "Document_Link": "https://example.com/minutes.pdf",
            "Filename": "04032024 minutes.pdf",
            "RecordType": "AgendaItemLocation",
        },
        source_tag="council",
        enrichment=enrichment,
    )
    assert row["Summary"] == "Long descriptive summary of the ordinance item"
    assert row["ActionTaken"] == "Passed first reading of Ordinance No. 2024-05"
    assert row["MotionText"] == "Motion to pass first reading"
    assert row["Latitude"] == ""
    assert row["FactCategory"] == "legislative_ordinance"
    assert row["RecordId"] == "council:1007"


def test_transform_enriches_from_normalized_tables():
    source_dir = config.NORMALIZED_COUNCIL_DIR
    enrichment = _load_source_enrichment(source_dir, source_dir / "extraction_review.csv")
    row = _transform_arcgis_row(
        {
            "Board": "Village Council",
            "AgendaItemID": "580",
            "MeetingDate": "2020-01-08",
            "AgendaItemNumber": "5",
            "AgendaItemType": "Contract Approval",
            "ProjectTitle": "Settlement Agreement",
            "ActionTaken": "Approved the settlement agreement",
            "Location": "20170 South Tamiami Trail, Estero, FL",
            "Latitude": "26.446",
            "Longitude": "-81.815",
            "GeocodeConfidence": "1.0",
            "Document_Link": "https://example.com/minutes.pdf",
            "Filename": "2020-01-08 Council Meeting Approved Minutes.pdf",
            "RecordType": "AgendaItemLocation",
        },
        source_tag="council",
        enrichment=enrichment,
    )
    assert row["MeetingId"]
    assert row["MeetingTime"] or row["MeetingVenue"] or row["AddressRaw"]


def test_transform_flags_review_filename_with_reason():
    enrichment = SourceEnrichment(
        review_by_filename={"flagged.pdf": "Review item: weak extraction"},
    )
    row = _transform_arcgis_row(
        {
            "Board": "Village Council",
            "AgendaItemID": "2001",
            "MeetingDate": "2020-01-01",
            "Summary": "Budget amendment summary text here",
            "ActionTaken": "Approved budget amendment",
            "Location": "1 Main St",
            "GeocodeConfidence": "1.0",
            "Latitude": "26.43",
            "Longitude": "-81.78",
            "Document_Link": "https://example.com/minutes.pdf",
            "Filename": "flagged.pdf",
            "RecordType": "AgendaItemLocation",
        },
        source_tag="council",
        enrichment=enrichment,
    )
    assert row["ReviewRequired"] == "true"
    assert "weak extraction" in row["ReviewReason"]
    assert row["AiReady"] == "false"


def test_build_ai_gold_emits_schema_and_jsonl():
    build_silver()
    report = build_gold()

    assert config.GOLD_AI_PUBLIC.exists()
    assert config.GOLD_AI_JSONL.exists()
    assert report["ai"]["rows"] > 0

    with open(config.GOLD_AI_PUBLIC, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == AI_GOLD_FIELDS
    assert len(rows) == report["ai"]["rows"]

    jsonl_rows = [
        json.loads(line)
        for line in config.GOLD_AI_JSONL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(jsonl_rows) == len(rows)
    sample = jsonl_rows[0]
    assert sample["ids"]["item_id"]
    assert sample["facts"]["action_taken"] is not None
    assert sample["agenda_item"]["summary"] is not None
    assert "grounding" in sample

    manifest = json.loads(config.GOLD_SITE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["ai"]["rows"] == report["ai"]["rows"]

    # ML specificity: summary and action should often differ (not collapsed).
    distinct = sum(
        1 for r in rows
        if r.get("Summary") and r.get("ActionTaken") and r["Summary"] != r["ActionTaken"]
    )
    assert distinct > 50
