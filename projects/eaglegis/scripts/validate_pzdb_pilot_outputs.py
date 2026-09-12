from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    args = parse_args()
    base = Path(args.base)
    pdf_dir = Path(args.pdf_dir)
    metrics = collect_metrics(base, pdf_dir)
    report_path = base / "qa_validation_report.md"
    report_path.write_text(render_report(metrics), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Wrote {report_path}")
    failures = validation_failures(metrics, fail_on_missing_coordinates=args.fail_on_missing_coordinates)
    if failures:
        print("Validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate PZDB pilot pipeline CSV outputs.")
    parser.add_argument("--base", default="normalized_csv_pilot/pzdb_from_raw_verify", help="Pilot output directory.")
    parser.add_argument("--pdf-dir", default="data/raw/pzdb", help="Pilot PDF directory.")
    parser.add_argument(
        "--fail-on-missing-coordinates",
        action="store_true",
        help="Exit nonzero if arcgis_missing_coordinates.csv has data rows.",
    )
    return parser.parse_args()


def collect_metrics(base: Path, pdf_dir: Path) -> dict:
    meetings = read_csv(base / "meetings_v2.csv")
    items = read_csv(base / "agenda_items.csv")
    locations = read_csv(base / "locations_v2.csv")
    motions = read_csv(base / "motions.csv")
    arcgis = read_csv(base / "arcgis_agenda_map_data.csv")
    missing_arcgis = read_csv(base / "arcgis_missing_coordinates.csv")

    meeting_ids = {row["meeting_id"] for row in meetings}
    item_ids = {row["item_id"] for row in items}
    duplicate_items = [
        key for key, count in Counter((row["meeting_id"], row["summary"]) for row in items).items()
        if count > 1
    ]
    malformed_app_ids = [
        row for row in items
        if row.get("application_id")
        and not re.search(r"(DOS|LDO|DCI|COP|ADD|CPA|ZTA|DO|RFB|RFQ|CN|EC|STA|Resolution|Ordinance)", row["application_id"], re.I)
    ]
    pdfs = list(pdf_dir.rglob("*.pdf"))

    return {
        "pdf_count": len(pdfs),
        "meeting_count": len(meetings),
        "agenda_item_count": len(items),
        "location_count": len(locations),
        "motion_count": len(motions),
        "arcgis_row_count": len(arcgis),
        "arcgis_missing_coordinate_count": len(missing_arcgis),
        "blank_arcgis_latlon_count": sum(1 for row in arcgis if not row.get("Latitude") or not row.get("Longitude")),
        "board_id_counts": dict(Counter(row["board_id"] for row in meetings)),
        "status_counts": dict(Counter(row["status"] for row in meetings)),
        "item_type_counts": dict(Counter(row["item_type"] for row in items)),
        "items_without_application_id": sum(1 for row in items if not row.get("application_id")),
        "malformed_application_id_count": len(malformed_app_ids),
        "items_without_address": sum(1 for row in items if not row.get("address_raw")),
        "motions_with_vote_counts": sum(1 for row in motions if row.get("vote_yes") or row.get("vote_no") or row.get("vote_abstain")),
        "fk_bad_agenda_meeting": sum(1 for row in items if row.get("meeting_id") not in meeting_ids),
        "fk_bad_location_item": sum(1 for row in locations if row.get("item_id") not in item_ids),
        "fk_bad_motion_item": sum(1 for row in motions if row.get("item_id") not in item_ids),
        "duplicate_item_summary_count": len(duplicate_items),
        "meetings_without_items": [
            {"meeting_id": row["meeting_id"], "meeting_date": row["meeting_date"], "filename": row["filename"]}
            for row in meetings
            if not any(item["meeting_id"] == row["meeting_id"] for item in items)
        ],
    }


def validation_failures(metrics: dict, *, fail_on_missing_coordinates: bool) -> list[str]:
    failures: list[str] = []
    if metrics["pdf_count"] <= 0:
        failures.append("No source PDFs found.")
    if metrics["meeting_count"] <= 0:
        failures.append("No meetings were generated.")
    if metrics["agenda_item_count"] <= 0:
        failures.append("No agenda items were generated.")
    if metrics["location_count"] <= 0:
        failures.append("No locations were generated.")
    if metrics["arcgis_row_count"] <= 0:
        failures.append("No ArcGIS rows were generated.")
    if metrics["blank_arcgis_latlon_count"]:
        failures.append(f"{metrics['blank_arcgis_latlon_count']} ArcGIS rows have blank coordinates.")
    if fail_on_missing_coordinates and metrics["arcgis_missing_coordinate_count"]:
        failures.append(f"{metrics['arcgis_missing_coordinate_count']} location rows are missing coordinates.")
    if metrics["fk_bad_agenda_meeting"]:
        failures.append(f"{metrics['fk_bad_agenda_meeting']} agenda items reference missing meetings.")
    if metrics["fk_bad_location_item"]:
        failures.append(f"{metrics['fk_bad_location_item']} locations reference missing agenda items.")
    if metrics["fk_bad_motion_item"]:
        failures.append(f"{metrics['fk_bad_motion_item']} motions reference missing agenda items.")
    if metrics["malformed_application_id_count"]:
        failures.append(f"{metrics['malformed_application_id_count']} application IDs look malformed.")
    if metrics["duplicate_item_summary_count"]:
        failures.append(f"{metrics['duplicate_item_summary_count']} agenda item summaries are duplicated within a meeting.")
    return failures


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def render_report(metrics: dict) -> str:
    lines = [
        "# PZDB Pilot QA Validation",
        "",
        "## Metrics",
        "",
        f"- PDFs scanned: `{metrics['pdf_count']}`",
        f"- Meetings: `{metrics['meeting_count']}`",
        f"- Agenda items: `{metrics['agenda_item_count']}`",
        f"- Locations: `{metrics['location_count']}`",
        f"- Motions: `{metrics['motion_count']}`",
        f"- ArcGIS rows: `{metrics['arcgis_row_count']}`",
        f"- ArcGIS missing coordinates: `{metrics['arcgis_missing_coordinate_count']}`",
        f"- Blank ArcGIS lat/lon rows: `{metrics['blank_arcgis_latlon_count']}`",
        f"- Malformed application IDs: `{metrics['malformed_application_id_count']}`",
        f"- Motions with parsed vote counts: `{metrics['motions_with_vote_counts']}`",
        "",
        "## Integrity Checks",
        "",
        f"- Bad agenda item meeting refs: `{metrics['fk_bad_agenda_meeting']}`",
        f"- Bad location item refs: `{metrics['fk_bad_location_item']}`",
        f"- Bad motion item refs: `{metrics['fk_bad_motion_item']}`",
        f"- Duplicate item summaries within a meeting: `{metrics['duplicate_item_summary_count']}`",
        f"- Meetings without items: `{len(metrics['meetings_without_items'])}`",
        "",
        "## Remaining Watch Items",
        "",
        "- Items without addresses are expected for procedural, consent, and non-site-specific actions.",
        "- Motions without parsed vote counts generally lack explicit Aye/Nay sections in extracted text.",
        "- Duplicate item summaries should be manually reviewed when nonzero.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
