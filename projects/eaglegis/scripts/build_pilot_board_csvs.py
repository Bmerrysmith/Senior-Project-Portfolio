from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from build_normalized_csvs import NormalizedBuilder, arcgis_sort_key, arcgis_text
from eaglegis_pipeline.sources import PdfAsset, repo_relative_path
from eaglegis_pipeline.writer import write_csv


TABLE_FIELDS = {
    "meetings_v2.csv": [
        "meeting_id", "board_id", "format_id", "legacy_meeting_id", "title",
        "meeting_date", "meeting_time", "meeting_location", "pdf_url", "raw_text",
        "summary", "status", "filename", "notes",
    ],
    "agenda_items.csv": [
        "item_id", "meeting_id", "item_number", "item_type", "application_id",
        "applicant_name", "project_title", "district", "address_raw", "summary",
        "outcome", "motion_text", "vote_result", "created_at",
    ],
    "locations_v2.csv": [
        "location_id", "item_id", "address_raw", "address_normalized",
        "latitude", "longitude", "parcel_id", "geocode_confidence", "created_at",
    ],
    "motions.csv": [
        "motion_id", "item_id", "motion_text", "proposed_by", "seconded_by",
        "outcome", "vote_yes", "vote_no", "vote_abstain", "created_at",
    ],
}

ARCGIS_FIELDS = [
    "ProjectName", "Board", "MeetingFormat", "MeetingType", "MeetingDate",
    "ArcGIS_Date", "MeetingYear", "Status", "AgendaItemID", "AgendaItemNumber",
    "AgendaItemType", "ProjectTitle", "Summary", "ActionTaken", "Outcome",
    "MotionText", "ProposedBy", "SecondedBy", "VoteResult", "ApplicantName",
    "ApplicationID", "District", "LocationName", "Location", "Latitude",
    "Longitude", "GeocodeConfidence", "StaffCode", "Filename", "Document_Link",
    "RecordType",
]


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)

    if args.from_pdfs:
        pilot_meetings, agenda_items, locations, motions = build_from_pdfs(args)
    else:
        pilot_meetings, agenda_items, locations, motions = build_from_normalized_csvs(args)

    if args.renumber:
        pilot_meetings, agenda_items, locations, motions = renumber(
            pilot_meetings,
            agenda_items,
            locations,
            motions,
        )

    write_csv(out_dir / "meetings_v2.csv", pilot_meetings, TABLE_FIELDS["meetings_v2.csv"])
    write_csv(out_dir / "agenda_items.csv", agenda_items, TABLE_FIELDS["agenda_items.csv"])
    write_csv(out_dir / "locations_v2.csv", locations, TABLE_FIELDS["locations_v2.csv"])
    write_csv(out_dir / "motions.csv", motions, TABLE_FIELDS["motions.csv"])
    arcgis_rows, missing_coordinate_rows = build_arcgis_rows(
        pilot_meetings,
        agenda_items,
        locations,
        motions,
        args.board_name,
    )
    write_csv(out_dir / "arcgis_agenda_map_data.csv", arcgis_rows, ARCGIS_FIELDS)
    write_csv(out_dir / "arcgis_missing_coordinates.csv", missing_coordinate_rows, [
        "AgendaItemID", "MeetingDate", "ProjectTitle", "LocationName", "Location",
        "ActionTaken", "Document_Link",
    ])
    write_report(out_dir, args, pilot_meetings, agenda_items, locations, motions, arcgis_rows, missing_coordinate_rows)

    print(f"Wrote pilot CSVs to {out_dir}")
    print(f"Meetings: {len(pilot_meetings)}")
    print(f"Agenda items: {len(agenda_items)}")
    print(f"Locations: {len(locations)}")
    print(f"Motions: {len(motions)}")
    print(f"ArcGIS rows: {len(arcgis_rows)}")
    print(f"ArcGIS missing coordinates: {len(missing_coordinate_rows)}")


def build_from_normalized_csvs(args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    source_dir = Path(args.source_dir)
    boards = read_csv(source_dir / "boards.csv")
    board_ids = {
        row["board_id"]
        for row in boards
        if row.get("code") == args.board_code or row.get("name") == args.board_name
    }
    if not board_ids:
        raise SystemExit(f"No board found for code={args.board_code!r} or name={args.board_name!r}.")

    meetings = read_csv(source_dir / "meetings_v2.csv")
    pilot_meetings = [
        row for row in meetings
        if row.get("board_id") in board_ids
        and args.start_date <= (row.get("meeting_date") or "") <= args.end_date
        and filename_matches(row.get("filename") or "", args.filename_token)
    ]
    pilot_meetings.sort(key=lambda row: (row.get("meeting_date") or "", row.get("filename") or ""))

    meeting_ids = {row["meeting_id"] for row in pilot_meetings}
    agenda_items = [
        row for row in read_csv(source_dir / "agenda_items.csv")
        if row.get("meeting_id") in meeting_ids
    ]
    item_ids = {row["item_id"] for row in agenda_items}
    locations = [
        row for row in read_csv(source_dir / "locations_v2.csv")
        if row.get("item_id") in item_ids
    ]
    motions = [
        row for row in read_csv(source_dir / "motions.csv")
        if row.get("item_id") in item_ids
    ]
    return pilot_meetings, agenda_items, locations, motions


def build_from_pdfs(args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    source_rows = read_csv(Path(args.source_csv)) if Path(args.source_csv).exists() else []
    legacy_rows_by_date = index_legacy_rows_by_date(source_rows)
    assets = pilot_pdf_assets(Path(args.pdf_dir), args.filename_token, args.start_date, args.end_date)
    if not assets:
        raise SystemExit(
            f"No pilot PDFs found in {args.pdf_dir!r} for token={args.filename_token!r} "
            f"and date range {args.start_date}..{args.end_date}."
        )

    builder = NormalizedBuilder(source_rows=source_rows)
    for asset in assets:
        meeting_date = date_from_filename(asset.filename)
        builder.add_pdf(asset, legacy_rows_by_date.get(meeting_date, []))

    geocode_cache = Path(args.source_dir) / "geocoded_locations.csv"
    builder._apply_geocode_cache(geocode_cache)
    normalize_pilot_meetings(builder.meetings, args.board_name)
    return builder.meetings, builder.agenda_items, builder.locations_v2, builder.motions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a referentially aligned pilot board slice from normalized CSV outputs."
    )
    parser.add_argument("--source-dir", default="normalized_csv", help="Directory containing full normalized CSVs.")
    parser.add_argument("--source-csv", default="pdfs/Estero_Meetings_Final.csv", help="Legacy source CSV.")
    parser.add_argument("--pdf-dir", default="pdfs", help="Directory containing local PDFs.")
    parser.add_argument("--out-dir", default="normalized_csv_pilot", help="Directory for pilot CSVs.")
    parser.add_argument("--board-code", default="PZDB", help="Board code to include.")
    parser.add_argument(
        "--board-name",
        default="Planning Zoning & Design Board",
        help="Board name to include if code matching is unavailable.",
    )
    parser.add_argument("--start-date", default="2022-01-01", help="Inclusive start date.")
    parser.add_argument("--end-date", default="2025-12-31", help="Inclusive end date.")
    parser.add_argument(
        "--filename-token",
        default="PZDB",
        help="Optional filename token required for pilot meetings. Use an empty value to disable.",
    )
    parser.add_argument(
        "--renumber",
        action="store_true",
        help="Renumber meeting, item, location, and motion IDs from 1 for a clean pilot import.",
    )
    parser.add_argument(
        "--from-pdfs",
        action="store_true",
        help="Build the pilot slice directly from local PDFs instead of filtering existing normalized CSVs.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Missing required CSV: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def filename_matches(filename: str, token: str) -> bool:
    if not token:
        return True
    return token.lower() in filename.lower()


def date_from_filename(filename: str) -> str | None:
    match = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", filename)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    match = re.search(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", filename)
    if not match:
        return None
    month, day, year = match.groups()
    return f"{year}-{month}-{day}"


def pilot_pdf_assets(pdf_dir: Path, token: str, start_date: str, end_date: str) -> list[PdfAsset]:
    assets = []
    for path in sorted(pdf_dir.rglob("*.pdf")):
        if not filename_matches(path.name, token):
            continue
        meeting_date = date_from_filename(path.name)
        if not meeting_date or not (start_date <= meeting_date <= end_date):
            continue
        assets.append(PdfAsset(repo_relative_path(path), path.name, path.read_bytes()))
    return sorted(assets, key=lambda asset: (date_from_filename(asset.filename) or "", asset.filename))


def index_legacy_rows_by_date(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        meeting_type = row.get("MeetingType") or row.get("Meeting Type") or ""
        if "PZDB" not in meeting_type and "Planning" not in meeting_type:
            continue
        meeting_date = row.get("MeetingDate") or row.get("ArcGIS_Date") or row.get("DocDate") or ""
        if meeting_date:
            out[meeting_date].append(row)
    return out


def normalize_pilot_meetings(meetings: list[dict], board_name: str) -> None:
    for meeting in meetings:
        filename = meeting.get("filename") or ""
        if "pzdb" not in filename.lower():
            continue
        meeting["board_id"] = 2
        meeting["summary"] = board_name


def renumber(
    meetings: list[dict],
    agenda_items: list[dict],
    locations: list[dict],
    motions: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    meeting_map = {row["meeting_id"]: str(index) for index, row in enumerate(meetings, start=1)}
    item_map = {row["item_id"]: str(index) for index, row in enumerate(agenda_items, start=1)}
    location_map = {row["location_id"]: str(index) for index, row in enumerate(locations, start=1)}
    motion_map = {row["motion_id"]: str(index) for index, row in enumerate(motions, start=1)}

    renumbered_meetings = []
    for row in meetings:
        out = dict(row)
        out["legacy_meeting_id"] = row["meeting_id"]
        out["meeting_id"] = meeting_map[row["meeting_id"]]
        renumbered_meetings.append(out)

    renumbered_items = []
    for row in agenda_items:
        out = dict(row)
        out["item_id"] = item_map[row["item_id"]]
        out["meeting_id"] = meeting_map[row["meeting_id"]]
        renumbered_items.append(out)

    renumbered_locations = []
    for row in locations:
        out = dict(row)
        out["location_id"] = location_map[row["location_id"]]
        out["item_id"] = item_map[row["item_id"]]
        renumbered_locations.append(out)

    renumbered_motions = []
    for row in motions:
        out = dict(row)
        out["motion_id"] = motion_map[row["motion_id"]]
        out["item_id"] = item_map[row["item_id"]]
        renumbered_motions.append(out)

    return renumbered_meetings, renumbered_items, renumbered_locations, renumbered_motions


def build_arcgis_rows(
    meetings: list[dict],
    agenda_items: list[dict],
    locations: list[dict],
    motions: list[dict],
    board_name: str,
) -> tuple[list[dict], list[dict]]:
    meetings_by_id = {str(row["meeting_id"]): row for row in meetings}
    motions_by_item = {str(row["item_id"]): row for row in motions}
    locations_by_item: dict[str, list[dict]] = defaultdict(list)
    for location in locations:
        locations_by_item[str(location.get("item_id"))].append(location)

    rows: list[dict] = []
    missing: list[dict] = []
    for item in agenda_items:
        meeting = meetings_by_id.get(str(item.get("meeting_id")), {})
        motion = motions_by_item.get(str(item.get("item_id")), {})
        item_locations = locations_by_item.get(str(item.get("item_id")), [])
        for location in item_locations:
            row = {
                "ProjectName": arcgis_text(item.get("project_title"), 250),
                "Board": board_name,
                "MeetingFormat": "Cancelled" if meeting.get("status") == "Cancelled" else "Regular Meeting",
                "MeetingType": meeting.get("summary") or board_name,
                "MeetingDate": meeting.get("meeting_date"),
                "ArcGIS_Date": meeting.get("meeting_date"),
                "MeetingYear": str(meeting.get("meeting_date") or "")[:4],
                "Status": meeting.get("status"),
                "AgendaItemID": item.get("item_id"),
                "AgendaItemNumber": item.get("item_number"),
                "AgendaItemType": item.get("item_type"),
                "ProjectTitle": arcgis_text(item.get("project_title"), 250),
                "Summary": arcgis_text(item.get("summary"), 500),
                "ActionTaken": arcgis_text(item.get("outcome"), 1000),
                "Outcome": arcgis_text(item.get("outcome"), 1000),
                "MotionText": arcgis_text(motion.get("motion_text") or item.get("motion_text"), 1000),
                "ProposedBy": motion.get("proposed_by"),
                "SecondedBy": motion.get("seconded_by"),
                "VoteResult": item.get("vote_result"),
                "ApplicantName": arcgis_text(item.get("applicant_name"), 250),
                "ApplicationID": item.get("application_id"),
                "District": item.get("district"),
                "LocationName": arcgis_text(location.get("address_normalized") or location.get("address_raw"), 250),
                "Location": arcgis_text(location.get("address_normalized") or location.get("address_raw"), 250),
                "Latitude": location.get("latitude"),
                "Longitude": location.get("longitude"),
                "GeocodeConfidence": location.get("geocode_confidence"),
                "StaffCode": item.get("staff_code"),
                "Filename": meeting.get("filename"),
                "Document_Link": meeting.get("pdf_url"),
                "RecordType": "AgendaItemLocation",
            }
            if row["Latitude"] not in (None, "") and row["Longitude"] not in (None, ""):
                rows.append(row)
            else:
                missing.append({
                    "AgendaItemID": item.get("item_id"),
                    "MeetingDate": meeting.get("meeting_date"),
                    "ProjectTitle": item.get("project_title"),
                    "LocationName": location.get("address_normalized") or location.get("address_raw"),
                    "Location": location.get("address_normalized") or location.get("address_raw"),
                    "ActionTaken": item.get("outcome"),
                    "Document_Link": meeting.get("pdf_url"),
                })

    return sorted(rows, key=arcgis_sort_key), sorted(missing, key=arcgis_sort_key)


def write_report(
    out_dir: Path,
    args: argparse.Namespace,
    meetings: list[dict],
    agenda_items: list[dict],
    locations: list[dict],
    motions: list[dict],
    arcgis_rows: list[dict],
    missing_coordinate_rows: list[dict],
) -> None:
    meeting_ids = {row["meeting_id"] for row in meetings}
    item_ids = {row["item_id"] for row in agenda_items}
    bad_item_meetings = [row for row in agenda_items if row.get("meeting_id") not in meeting_ids]
    bad_location_items = [row for row in locations if row.get("item_id") not in item_ids]
    bad_motion_items = [row for row in motions if row.get("item_id") not in item_ids]

    lines = [
        "# Pilot CSV Validation",
        "",
        f"- Board: `{args.board_code}`",
        f"- Date range: `{args.start_date}` to `{args.end_date}`",
        f"- Filename token: `{args.filename_token}`",
        f"- Source mode: `{'pdfs' if args.from_pdfs else 'normalized_csv'}`",
        f"- Renumbered IDs: `{args.renumber}`",
        f"- Meetings: `{len(meetings)}`",
        f"- Agenda items: `{len(agenda_items)}`",
        f"- Locations: `{len(locations)}`",
        f"- Motions: `{len(motions)}`",
        f"- ArcGIS rows: `{len(arcgis_rows)}`",
        f"- ArcGIS missing coordinate rows: `{len(missing_coordinate_rows)}`",
        f"- Agenda items with missing meeting parent: `{len(bad_item_meetings)}`",
        f"- Locations with missing agenda item parent: `{len(bad_location_items)}`",
        f"- Motions with missing agenda item parent: `{len(bad_motion_items)}`",
    ]
    if meetings:
        lines.extend([
            f"- First meeting date: `{min(row.get('meeting_date') or '' for row in meetings)}`",
            f"- Last meeting date: `{max(row.get('meeting_date') or '' for row in meetings)}`",
        ])
    if not agenda_items and not args.from_pdfs:
        lines.extend([
            "",
            "Note: this pilot slice has no agenda item rows in the current normalized source outputs.",
            "The local source CSV marks PZDB actions as `No action extracted - verify PDF`, and the local `pdfs/` folder does not contain PZDB PDFs.",
        ])

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
