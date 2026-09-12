from __future__ import annotations

import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_normalized_csvs import (
    NormalizedBuilder,
    infer_application_id,
    infer_vote_counts,
    normalize_address_candidate,
)
from eaglegis_pipeline.classifiers import extract_address_candidates
from eaglegis_pipeline.extractors import extract_agenda_entries, raw_pdf_url
from eaglegis_pipeline.sources import PdfAsset, iter_local_pdfs


class PipelineParserTests(unittest.TestCase):
    def test_application_id_ignores_common_word_fragments(self) -> None:
        self.assertIsNone(infer_application_id("Approved with staff conditions."))
        self.assertIsNone(infer_application_id("Standards for elevated single-family homes."))
        self.assertIsNone(infer_application_id("The site plan was discussed."))

    def test_application_id_extracts_pzdb_identifiers(self) -> None:
        self.assertEqual(
            infer_application_id("Development Order (DOS2023-E012) with staff conditions."),
            "DOS2023-E012",
        )
        self.assertEqual(
            infer_application_id("Limited Development Order LDO2024-E041 was approved."),
            "LDO2024-E041",
        )
        self.assertEqual(
            infer_application_id("Outdoor Consumption on Premises COP2023-E002."),
            "COP2023-E002",
        )

    def test_fallback_approved_does_not_capture_board_header(self) -> None:
        text = (
            "APPROVED BY BOARD FEBRUARY 13, 2024 Planning Zoning and Design Board Meeting "
            "Village of Estero 9401 Corkscrew Palms Circle Estero, FL 33928 "
            "1. CALL TO ORDER 2. ROLL CALL"
        )
        self.assertEqual(extract_agenda_entries(text), [])

    def test_action_entry_preserves_following_vote_text(self) -> None:
        text = (
            "Motion: Motion to approve. Motion by: Board Member Jones Seconded by: Board Member Wallace "
            "Action: Approved the Development Order with staff conditions. "
            "Vote: Aye: Board Members Jones, Wallace Nay: None Abstentions: None "
            "Public Input None."
        )
        entries = extract_agenda_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].action_text, "Approved the Development Order with staff conditions")
        self.assertIn("Aye: Board Members Jones, Wallace", entries[0].vote_text or "")

    def test_action_without_vote_stops_at_next_numbered_heading(self) -> None:
        text = (
            "Motion: Motion to continue. Action: Approved to continue the meeting until 9:15 pm. "
            "7. WORKSHOP (1) Culver's Coconut Point Development Order (District 6) "
            "8400 Murano Del Lago Dr, east of US 41."
        )
        entries = extract_agenda_entries(text)
        self.assertEqual(entries[0].action_text, "Approved to continue the meeting until 9:15 pm")

    def test_action_without_vote_stops_at_parenthetical_heading(self) -> None:
        text = (
            "Action: Appointed Michael Sheeley as Vice Chairman. "
            "(a) Aldi - Development Order (Pending Submittal) (District 5) Located east of Stoneybrook."
        )
        entries = extract_agenda_entries(text)
        self.assertEqual(entries[0].action_text, "Appointed Michael Sheeley as Vice Chairman")

    def test_section_fallback_extracts_non_action_location_item(self) -> None:
        text = (
            "PUBLIC INFORMATION MEETINGS (a) Estero Storage LLC - Zoning Amendment "
            "(No application submitted) (District 4) 10251 Arcos Avenue located on a 7-acre "
            "vacant site east of the Estero Medical Center. Staff Presentation/Comments Mary Gibbs. "
            "BOARD COMMUNICATIONS Next meeting."
        )
        entries = extract_agenda_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertIn("No formal action recorded", entries[0].action_text)
        self.assertIn("10251 Arcos Avenue", entries[0].action_text)

    def test_address_candidates_include_estero_street_addresses(self) -> None:
        text = (
            "Culver's Coconut Point Development Order at 8400 Murano Del Lago Dr, "
            "east of US 41 and south of Pelican Colony Blvd."
        )
        self.assertIn("8400 Murano Del Lago Dr", extract_address_candidates(text))

    def test_address_candidates_include_tamiami_trail(self) -> None:
        text = "19701 S. Tamiami Trail, located east on US 41, north of the Vines entrance."
        self.assertIn("19701 S. Tamiami Trail", extract_address_candidates(text))

    def test_address_candidate_normalizes_ocr_dropped_digit(self) -> None:
        self.assertEqual(normalize_address_candidate("0251 Arcos Avenue"), "10251 Arcos Avenue")

    def test_vote_count_parses_aye_nay_abstentions(self) -> None:
        yes, no, abstain = infer_vote_counts(
            "Vote: Aye: Board Members Jones, Jeannin, Naratil, Chairman Wood "
            "Nay: Board Member Wallace Abstentions: None"
        )
        self.assertEqual(yes, 4)
        self.assertEqual(no, 1)
        self.assertEqual(abstain, 0)

    def test_empty_abstentions_stop_at_numbered_heading(self) -> None:
        yes, no, abstain = infer_vote_counts(
            "Vote: Aye: Board Members Jones, Jeannin Nay: Board Member Wallace "
            "Abstentions: 8. PUBLIC INPUT None."
        )
        self.assertEqual(yes, 2)
        self.assertEqual(no, 1)
        self.assertEqual(abstain, 0)

    def test_empty_abstentions_stop_at_parenthetical_heading(self) -> None:
        yes, no, abstain = infer_vote_counts(
            "Vote: Aye: Board Members Jones, Jeannin Nay: Abstentions: "
            "(b) Development Order - Arcos Executive Office (DOS2017-E006)"
        )
        self.assertEqual(yes, 2)
        self.assertEqual(no, 0)
        self.assertEqual(abstain, 0)

    def test_empty_abstentions_stop_at_page_header(self) -> None:
        yes, no, abstain = infer_vote_counts(
            "Vote: Aye: Board Members Jones, Jeannin Nay: Board Member Wallace "
            "Abstentions: Planning Zoning and Design Board Minutes - July 11, 2023 Page 5 of 6"
        )
        self.assertEqual(yes, 2)
        self.assertEqual(no, 1)
        self.assertEqual(abstain, 0)

    def test_local_pdf_discovery_is_recursive(self) -> None:
        root = ROOT / ".test_tmp" / uuid4().hex
        try:
            nested = root / "2024"
            nested.mkdir(parents=True)
            pdf_path = nested / "20240213 PZDB Minutes.pdf"
            pdf_path.write_bytes(b"%PDF-test")
            assets = iter_local_pdfs(root)
            self.assertEqual([asset.filename for asset in assets], ["20240213 PZDB Minutes.pdf"])
        finally:
            if root.exists():
                for path in sorted(root.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    else:
                        path.rmdir()
                root.rmdir()

    def test_raw_pdf_url_preserves_nested_pilot_path(self) -> None:
        self.assertEqual(
            raw_pdf_url("data/raw/pzdb/2024/20240213 PZDB Minutes.pdf"),
            "https://raw.githubusercontent.com/EagleGIS-FGCU/EagleGIS/main/data/raw/pzdb/2024/20240213%20PZDB%20Minutes.pdf",
        )

    def test_raw_pdf_url_keeps_legacy_pdf_default(self) -> None:
        self.assertEqual(
            raw_pdf_url("01032024 minutes.pdf"),
            "https://raw.githubusercontent.com/EagleGIS-FGCU/EagleGIS/main/pdfs/01032024%20minutes.pdf",
        )

    def test_builder_skips_exact_duplicate_agenda_items(self) -> None:
        builder = NormalizedBuilder(source_rows=[])
        kwargs = {
            "meeting_id": 1,
            "item_order": 1,
            "meeting_type": "Planning Zoning & Design Board",
            "item_title": "Development Order (DOS2024-E001)",
            "action_text": "Approved the Development Order with staff conditions",
            "vote_text": None,
            "staff_code": None,
            "needs_ocr": False,
            "date_missing": False,
            "used_csv_fallback": False,
            "fallback_projects": [],
            "fallback_locations": [],
            "asset": PdfAsset(path="test.pdf", filename="test.pdf", data=b""),
        }
        builder._add_action(**kwargs)
        builder._add_action(**kwargs)
        self.assertEqual(len(builder.agenda_items), 1)

    def test_location_extraction_uses_agenda_title_context(self) -> None:
        builder = NormalizedBuilder(source_rows=[])
        builder._add_action(
            meeting_id=1,
            item_order=1,
            meeting_type="Planning Zoning & Design Board",
            item_title=(
                "Estero Townhomes EPD - Rezoning (DCI2024-E003) (District 4) "
                "21.4 acres located on the northeast corner of Corkscrew Road and Sandy Lane"
            ),
            action_text="Approved Development Order with staff stipulations.",
            vote_text="Aye: Board Members Jones Nay: Abstentions:",
            staff_code=None,
            needs_ocr=False,
            date_missing=False,
            used_csv_fallback=False,
            fallback_projects=[],
            fallback_locations=[],
            asset=PdfAsset(path="test.pdf", filename="test.pdf", data=b""),
        )

        self.assertEqual(
            builder.agenda_items[0]["address_raw"],
            "Estero Townhomes EPD site, 9301 Corkscrew Road, Estero, FL",
        )
        self.assertEqual(len(builder.locations_v2), 1)
        self.assertEqual(builder.locations_v2[0]["latitude"], 26.432264859989)
        self.assertEqual(builder.locations_v2[0]["longitude"], -81.801155452524)

    def test_long_public_comment_context_keeps_agenda_heading(self) -> None:
        text = (
            "(a) Estero Townhomes EPD - Rezoning (DCI2024-E003) (District 4) "
            "21.4 acres located on the northeast corner of Corkscrew Road and Sandy Lane. "
            "Staff Presentation/Comments Mary Gibbs. Public Comment "
            + " ".join(f"Speaker {i}, Estero" for i in range(180))
            + " Board Questions or Comments Board Members. Motion: Motion to approve. "
            "Motion by: Board Member Jones Seconded by: Board Member Wallace "
            "Action: Approved Development Order with staff stipulations. "
            "Vote: Aye: Board Members Jones and Wallace Nay: Abstentions:"
        )

        entries = extract_agenda_entries(text)

        self.assertEqual(len(entries), 1)
        self.assertIn("Corkscrew Road", entries[0].title)

    def test_us_41_sentence_does_not_split_agenda_title(self) -> None:
        text = (
            "(c) 8111 Broadway East Development Order Amendment #1 (DOS2019-E004) "
            "(District 4) 8111 Broadway East is a 1-acre site located 200 feet east of US 41. "
            "It was developed in 1983 by the U.S. Federal Government for a Post Office. "
            "Staff Presentation/Comments Mary Gibbs. Motion: Motion to approve. "
            "Motion by: Board Member Jones Seconded by: Board Member Wallace "
            "Action: Approved Development Order with conditions. "
            "Vote: Aye: Board Members Jones and Wallace Nay: Abstentions:"
        )

        entries = extract_agenda_entries(text)

        self.assertEqual(len(entries), 1)
        self.assertIn("8111 Broadway East", entries[0].title)
        self.assertIn("US 41", entries[0].title)

    def test_numbered_parenthetical_agenda_item_is_title_marker(self) -> None:
        text = (
            "(1) Development Order - Dunkin Donuts (DOS2022-E004) 10500 Corkscrew Road. "
            "Motion: Motion to approve. Action: Approved request with staff conditions. "
            "Vote: Aye: Board Members Jones Nay: Abstentions: "
            "(3) Land Development Code Amendment - Lot Coverage (Ordinance 2022-12). "
            "Motion: Motion to recommend approval of Ordinance 2022-12 to Council. "
            "Action: Recommended approval of Ordinance 2022-12 to Council. "
            "Vote: Aye: Board Members Jones Nay: Abstentions:"
        )

        entries = extract_agenda_entries(text)

        self.assertEqual(len(entries), 2)
        self.assertIn("Land Development Code Amendment", entries[1].title)
        self.assertNotIn("10500 Corkscrew Road", entries[1].title)


if __name__ == "__main__":
    unittest.main()
