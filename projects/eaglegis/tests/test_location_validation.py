"""Focused tests for strict location-validation behavior."""
from __future__ import annotations

from app.pipeline.load.silver import build_silver
from app.pipeline.publish.gold import build_gold
from app.pipeline.run import run


def test_build_gold_emits_location_quality_summary():
    build_silver()
    report = build_gold()
    quality = report["location_quality"]
    assert set(
        [
            "exact_location_id",
            "project_fallback",
            "geocoded",
            "text_only",
            "missing",
            "with_coords",
            "outside_bbox_or_invalid",
            "strict_violations",
        ]
    ).issubset(quality.keys())


def test_run_strict_exits_5_on_location_violations(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.run.build_silver",
        lambda: {"meetings": {"rejects": 0}, "documents": {"rejects": 0}},
    )
    monkeypatch.setattr(
        "app.pipeline.run.run_geocode",
        lambda **kwargs: {"strict_violations": ["geo mismatch"], "geocoded_location_ids": []},
    )
    monkeypatch.setattr(
        "app.pipeline.run.build_gold",
        lambda **kwargs: {"location_quality": {"strict_violations": ["unresolved"]}},
    )
    monkeypatch.setattr("app.pipeline.run._maybe_run_supabase_stages", lambda **kwargs: (False, False))
    monkeypatch.setattr("app.pipeline.run._write_manifest", lambda payload: None)

    rc = run(strict=True)
    assert rc == 5
