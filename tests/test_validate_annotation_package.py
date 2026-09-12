import copy
import json
import tempfile
import unittest
from pathlib import Path

from agrinav.data.validate_annotation_package import (
    load_ontology,
    validate_packages,
    validate_record,
    validate_split_groups,
)

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = ROOT / "data" / "ontology.v1.json"


def object_attributes(**overrides: object) -> dict:
    attributes = {
        "source_object_id": None,
        "species": None,
        "growth_stage": None,
        "occlusion": "none",
        "truncated": False,
        "annotation_confidence": "certain",
        "treatment_eligible": None,
        "human_edit_action": "added",
    }
    attributes.update(overrides)
    return attributes


def base_record() -> dict:
    return {
        "schema_version": "agrinav.annotation_record.v1",
        "record_id": "record-001",
        "image_id": "image-001",
        "source": {
            "dataset_id": "local-pilot",
            "dataset_version": None,
            "image_uri": "images/image-001.png",
            "source_image_sha256": "a" * 64,
            "width": 100,
            "height": 80,
            "country": None,
            "site_id": None,
            "field_id": None,
            "session_id": None,
            "capture_pass_id": None,
            "frame_id": None,
            "source_photo_id": None,
            "group_id": "capture-group-001",
            "split": "train",
            "capture_metadata": None,
        },
        "provenance": {
            "proposal_model_id": None,
            "proposal_model_revision": None,
            "proposal_method": "manual",
            "prompt": None,
            "thresholds": None,
            "generated_at": None,
            "original_proposal": None,
            "human_edit_state": "human_only",
        },
        "review": {
            "annotator_id": "annotator-a",
            "annotator_completed_at": "2026-07-20T12:05:00Z",
            "reviewer_id": "reviewer-b",
            "reviewed_at": "2026-07-20T12:10:00Z",
            "review_status": "accepted",
            "annotation_version": "pilot-v1",
            "guide_version": "v1",
        },
        "verified_empty": None,
        "unusable": False,
        "annotations": [
            {
                "annotation_id": "ann-001",
                "label": "rice_protect",
                "biological_class": "rice",
                "decision_role": "protect",
                "geometry": {"type": "polygon", "polygon": [10, 10, 30, 10, 30, 30, 10, 30]},
                "attributes": object_attributes(treatment_eligible=False),
            }
        ],
    }


class AnnotationRecordValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ontology = load_ontology(ONTOLOGY_PATH)

    def assertValid(self, record: dict) -> None:
        self.assertEqual([], validate_record(record, self.ontology))

    def assertInvalidContains(self, record: dict, fragment: str) -> None:
        errors = validate_record(record, self.ontology)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_human_verified_empty_is_valid_and_can_still_contain_rice(self) -> None:
        record = base_record()
        record["verified_empty"] = True
        self.assertValid(record)

    def test_unknown_vegetation_is_safe_nonactionable(self) -> None:
        record = base_record()
        record["annotations"] = [
            {
                "annotation_id": "ann-unknown",
                "label": "unknown_vegetation",
                "biological_class": "unknown_vegetation",
                "decision_role": "unknown_nonactionable",
                "geometry": {"type": "polygon", "polygon": [0, 0, 8, 0, 8, 6, 0, 6]},
                "attributes": object_attributes(),
            }
        ]
        self.assertValid(record)

    def test_ood_record_with_non_target_aquatic_mask_is_valid(self) -> None:
        record = base_record()
        record["source"]["split"] = "ood"
        record["source"]["country"] = "Japan"
        record["annotations"] = [
            {
                "annotation_id": "ann-aquatic",
                "label": "non_target_aquatic",
                "biological_class": "duckweed_or_aquatic_vegetation",
                "decision_role": "unknown_nonactionable",
                "geometry": {
                    "type": "semantic_mask",
                    "rle": {"size": [80, 100], "counts": [10, 3, 7987]},
                },
                "attributes": object_attributes(),
            }
        ]
        self.assertValid(record)

    def test_missing_nullable_source_field_is_not_silently_accepted(self) -> None:
        record = base_record()
        del record["source"]["site_id"]
        self.assertInvalidContains(record, "explicit null")

    def test_unexpected_fields_are_rejected_like_the_json_schema(self) -> None:
        record = base_record()
        record["source"]["mystery_lineage"] = "not-versioned"
        self.assertInvalidContains(record, "unexpected field")

    def test_all_required_object_attributes_are_enforced(self) -> None:
        for field in object_attributes():
            with self.subTest(field=field):
                record = base_record()
                del record["annotations"][0]["attributes"][field]
                self.assertInvalidContains(record, f"attributes.{field}: missing required field")

    def test_object_attribute_enums_and_types_are_enforced(self) -> None:
        invalid_values = {
            "source_object_id": 7,
            "species": "",
            "growth_stage": [],
            "occlusion": "hidden",
            "truncated": 1,
            "annotation_confidence": "maybe",
            "treatment_eligible": "yes",
            "human_edit_action": "auto_accepted",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                record = base_record()
                record["annotations"][0]["attributes"][field] = value
                self.assertInvalidContains(record, f"attributes.{field}")

    def test_accepted_annotation_requires_per_object_human_edit_action(self) -> None:
        record = base_record()
        record["annotations"][0]["attributes"]["human_edit_action"] = None
        self.assertInvalidContains(record, "required for accepted/adjudicated records")

    def test_non_null_treatment_eligibility_requires_independent_reviewer(self) -> None:
        record = base_record()
        record["review"]["reviewer_id"] = None
        record["review"]["reviewed_at"] = None
        self.assertInvalidContains(record, "requires an independent reviewer")

    def test_proposal_linked_edit_action_requires_source_object_id(self) -> None:
        record = base_record()
        record["annotations"][0]["attributes"]["human_edit_action"] = "edited"
        self.assertInvalidContains(record, "source_object_id: required")

    def test_label_biology_and_decision_role_must_match_ontology(self) -> None:
        record = base_record()
        record["annotations"][0]["decision_role"] = "target"
        self.assertInvalidContains(record, "requires biological_class")

    def test_verified_empty_rejects_weed_target(self) -> None:
        record = base_record()
        record["verified_empty"] = True
        record["annotations"][0].update(
            {
                "label": "weed_target",
                "biological_class": "weed",
                "decision_role": "target",
            }
        )
        self.assertInvalidContains(record, "cannot coexist")

    def test_verified_empty_false_requires_accepted_weed(self) -> None:
        record = base_record()
        record["verified_empty"] = False
        self.assertInvalidContains(record, "false requires at least one")

        record["annotations"][0].update(
            {
                "label": "weed_target",
                "biological_class": "weed",
                "decision_role": "target",
            }
        )
        self.assertValid(record)

        record["review"]["review_status"] = "in_review"
        self.assertInvalidContains(record, "false requires accepted/adjudicated")

    def test_deleted_weed_proposal_does_not_conflict_with_verified_empty(self) -> None:
        record = base_record()
        record["verified_empty"] = True
        record["annotations"][0].update(
            {
                "label": "weed_target",
                "biological_class": "weed",
                "decision_role": "target",
                "geometry": {"type": "bbox", "bbox": [10, 10, 20, 20]},
                "attributes": object_attributes(
                    source_object_id="proposal-weed-1",
                    human_edit_action="deleted",
                ),
            }
        )
        self.assertValid(record)

    def test_model_silence_cannot_establish_verified_empty(self) -> None:
        record = base_record()
        record["verified_empty"] = True
        record["annotations"] = []
        record["provenance"].update(
            {
                "proposal_model_id": "org/model",
                "proposal_model_revision": "abc123",
                "proposal_method": "model_silence",
                "prompt": "weed",
                "thresholds": {"box": 0.4},
                "generated_at": "2026-07-20T12:00:00Z",
                "original_proposal": [],
                "human_edit_state": "accepted_unchanged",
            }
        )
        self.assertInvalidContains(record, "model silence")

    def test_accepted_model_assisted_record_requires_reviewer(self) -> None:
        record = base_record()
        record["provenance"].update(
            {
                "proposal_model_id": "org/model",
                "proposal_model_revision": "rev-1",
                "proposal_method": "model_assisted",
                "prompt": "rice . weed . unknown vegetation",
                "thresholds": {"box": 0.35, "text": 0.25},
                "generated_at": "2026-07-20T12:00:00Z",
                "original_proposal": {"objects": [{"label": "plant", "score": 0.9}]},
                "human_edit_state": "edited",
            }
        )
        record["review"]["reviewer_id"] = None
        self.assertInvalidContains(record, "require a human reviewer")

    def test_model_derived_record_requires_prompt_and_nonempty_thresholds(self) -> None:
        record = base_record()
        record["provenance"].update(
            {
                "proposal_model_id": "org/model",
                "proposal_model_revision": "rev-1",
                "proposal_method": "model_assisted",
                "prompt": None,
                "thresholds": {},
                "generated_at": "2026-07-20T12:00:00Z",
                "original_proposal": {"objects": []},
                "human_edit_state": "edited",
            }
        )
        errors = validate_record(record, self.ontology)
        self.assertTrue(any("provenance.prompt: required" in error for error in errors), errors)
        self.assertTrue(any("thresholds: model-derived" in error for error in errors), errors)

    def test_imported_unreviewed_bbox_proposal_is_valid(self) -> None:
        record = base_record()
        record["provenance"].update(
            {
                "proposal_method": "imported",
                "original_proposal": {"source_object_id": "coco-ann-17", "bbox": [1, 2, 7, 8]},
                "human_edit_state": "unreviewed",
            }
        )
        record["review"] = {
            "annotator_id": None,
            "annotator_completed_at": None,
            "reviewer_id": None,
            "reviewed_at": None,
            "review_status": "unreviewed",
            "annotation_version": None,
            "guide_version": None,
        }
        record["annotations"][0]["geometry"] = {"type": "bbox", "bbox": [1, 2, 7, 8]}
        record["annotations"][0]["attributes"] = object_attributes(
            source_object_id="coco-ann-17",
            human_edit_action=None,
        )
        self.assertValid(record)

    def test_accepted_bbox_is_not_canonical_geometry(self) -> None:
        record = base_record()
        record["annotations"][0]["geometry"] = {"type": "bbox", "bbox": [1, 2, 7, 8]}
        self.assertInvalidContains(record, "accepted label 'rice_protect' requires")

    def test_accepted_geometry_must_match_each_label_ontology(self) -> None:
        record = base_record()
        record["annotations"][0].update(
            {
                "label": "weed_target",
                "biological_class": "weed",
                "decision_role": "target",
                "geometry": {
                    "type": "semantic_mask",
                    "rle": {"size": [80, 100], "counts": [0, 1, 7999]},
                },
            }
        )
        self.assertInvalidContains(record, "accepted label 'weed_target' requires")

    def test_unusable_image_conflicts_are_rejected(self) -> None:
        record = base_record()
        record["unusable"] = True
        self.assertInvalidContains(record, "unusable images cannot be accepted")

        record = base_record()
        record["unusable"] = True
        record["verified_empty"] = True
        self.assertInvalidContains(record, "unusable images must remain unverified")

        record = base_record()
        record["review"]["review_status"] = "rejected_unusable"
        self.assertInvalidContains(record, "requires unusable=true")

    def test_rejected_unusable_record_is_valid_failure_slice(self) -> None:
        record = base_record()
        record["unusable"] = True
        record["annotations"] = []
        record["review"]["review_status"] = "rejected_unusable"
        self.assertValid(record)

    def test_bbox_bounds_and_polygon_area_are_checked(self) -> None:
        record = base_record()
        record["annotations"][0]["geometry"] = {"type": "bbox", "bbox": [99, 79, 2, 2]}
        self.assertInvalidContains(record, "outside")
        record["annotations"][0]["geometry"] = {"type": "polygon", "polygon": [1, 1, 2, 2, 3, 3]}
        self.assertInvalidContains(record, "zero area")

    def test_mask_size_coverage_and_nonempty_are_checked(self) -> None:
        record = base_record()
        record["annotations"][0]["geometry"] = {
            "type": "instance_mask",
            "rle": {"size": [79, 100], "counts": [8000]},
        }
        errors = validate_record(record, self.ontology)
        self.assertTrue(any("must equal image" in error for error in errors), errors)
        self.assertTrue(any("mask is empty" in error for error in errors), errors)
        record["annotations"][0]["geometry"]["rle"] = {
            "size": [80, 100],
            "counts": "P",
        }
        self.assertInvalidContains(record, "invalid compressed COCO RLE")

    def test_annotation_ids_must_be_unique_within_record(self) -> None:
        record = base_record()
        record["annotations"].append(copy.deepcopy(record["annotations"][0]))
        self.assertInvalidContains(record, "duplicate annotation ID")


class PackageValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_jsonl(self, name: str, records: list[dict]) -> Path:
        path = self.root / name
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    def test_package_annotation_ids_are_globally_unique(self) -> None:
        first = base_record()
        second = copy.deepcopy(first)
        second["record_id"] = "record-002"
        second["image_id"] = "image-002"
        second["source"]["source_image_sha256"] = "b" * 64
        path = self._write_jsonl("annotations.jsonl", [first, second])
        errors = validate_packages([path], ontology_path=ONTOLOGY_PATH)
        self.assertTrue(any("duplicate package annotation ID" in error for error in errors), errors)

    def test_package_image_ids_and_exact_source_hashes_are_unique(self) -> None:
        first = base_record()
        second = copy.deepcopy(first)
        second["record_id"] = "record-002"
        second["annotations"] = []
        path = self._write_jsonl("duplicate-images.jsonl", [first, second])
        errors = validate_packages([path], ontology_path=ONTOLOGY_PATH)
        self.assertTrue(any("image_id: duplicate" in error for error in errors), errors)
        self.assertTrue(any("duplicate exact image hash" in error for error in errors), errors)

    def test_same_source_hash_cannot_change_group_id(self) -> None:
        first = base_record()
        second = copy.deepcopy(first)
        second["record_id"] = "record-002"
        second["image_id"] = "image-002"
        second["source"]["group_id"] = "capture-group-OTHER"
        second["annotations"] = []
        path = self._write_jsonl("inconsistent-groups.jsonl", [first, second])
        errors = validate_packages([path], ontology_path=ONTOLOGY_PATH)
        self.assertTrue(any("inconsistent group IDs" in error for error in errors), errors)

    def test_split_overlap_is_detected_across_package_and_manifest(self) -> None:
        record = base_record()
        package = self._write_jsonl("train.jsonl", [record])
        manifest = self.root / "test_manifest.json"
        manifest.write_text(
            json.dumps({"samples": [{"group_id": "capture-group-001", "split": "test"}]}),
            encoding="utf-8",
        )
        errors = validate_packages(
            [package],
            ontology_path=ONTOLOGY_PATH,
            manifest_paths=[manifest],
            check_split_overlap=True,
        )
        self.assertTrue(any("split overlap" in error for error in errors), errors)

    def test_unassigned_group_does_not_create_false_overlap(self) -> None:
        documents = [
            ("pilot", {"samples": [{"group_id": "g-1", "split": "unassigned"}]}),
            ("test", {"samples": [{"group_id": "g-1", "split": "test"}]}),
        ]
        self.assertEqual([], validate_split_groups(documents))


if __name__ == "__main__":
    unittest.main()
