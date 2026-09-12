"""End-to-end smoke test: runs the pipeline against the real bronze CSVs
and asserts that the resulting silver outputs are sensible."""
import csv
import json
from pathlib import Path

from app.pipeline import config
from app.pipeline.run import run


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_pipeline_produces_silver_and_manifest():
    rc = run(strict=False, write_geocode_cache=False)
    assert rc == 0

    assert config.SILVER_MEETINGS.exists()
    assert config.SILVER_DOCUMENTS.exists()
    assert config.SILVER_DOCUMENTS_PLANNED.exists()
    assert config.SILVER_REJECTS.exists()

    meetings = _read_csv(config.SILVER_MEETINGS)
    docs_real = _read_csv(config.SILVER_DOCUMENTS)
    docs_planned = _read_csv(config.SILVER_DOCUMENTS_PLANNED)

    assert meetings, "silver meetings should be non-empty"
    assert all(m["meeting_id"] for m in meetings)
    assert all("Approve d" not in (m["action_taken"] or "") for m in meetings), \
        "split-verb OCR artifacts should be cleaned"

    assert all(d.get("link_status", "").lower() != "future placeholder" for d in docs_real)
    assert all(d.get("link_status", "").lower() == "future placeholder" for d in docs_planned)

    rejects = json.loads(config.SILVER_REJECTS.read_text())
    assert "meetings" in rejects and "documents" in rejects

    runs = sorted(config.RUNS_DIR.glob("*/manifest.json"))
    assert runs, "a run manifest should be written"
    manifest = json.loads(runs[-1].read_text())
    assert "stages" in manifest and "silver" in manifest["stages"]
    assert manifest["stages"]["silver"]["meetings"]["out"] == len(meetings)
    assert "geocode" in manifest["stages"]
    assert "gold" in manifest["stages"]
    assert "location_quality" in manifest
