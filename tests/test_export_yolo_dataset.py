"""Contract tests for the YOLOv8/v11 exporter.

The safety property under test: a *proposal* never becomes training truth by
default, geometry is never fabricated, and the sealed split is never re-mixed.
"""

import json
import tempfile
import unittest
from pathlib import Path

from agrinav.data.export_yolo_dataset import (
    DEFAULT_CLASSES,
    detect_line,
    export,
    record_label_lines,
)


def _obj(label, geometry, edit="accepted"):
    return {
        "annotation_id": f"o-{label}-{id(geometry)}",
        "label": label,
        "biological_class": "weed" if label == "weed_target" else "rice",
        "decision_role": "target" if label == "weed_target" else "protect",
        "geometry": geometry,
        "attributes": {
            "source_object_id": None,
            "species": None,
            "growth_stage": None,
            "occlusion": "none",
            "truncated": False,
            "annotation_confidence": "certain",
            "treatment_eligible": None,
            "human_edit_action": edit,
        },
    }


def _record(record_id, split, status, annotations, unusable=False, verified_empty=None):
    return {
        "schema_version": "agrinav.annotation_record.v1",
        "record_id": record_id,
        "image_id": f"{record_id}.png",
        "source": {
            "dataset_id": "t",
            "dataset_version": "1",
            "image_uri": f"{record_id}.png",
            "source_image_sha256": "0" * 64,
            "width": 100,
            "height": 100,
            "country": None,
            "site_id": None,
            "field_id": None,
            "session_id": None,
            "capture_pass_id": None,
            "frame_id": None,
            "source_photo_id": None,
            "group_id": record_id,
            "split": split,
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
            "annotator_id": "a",
            "annotator_completed_at": None,
            "reviewer_id": "r",
            "reviewed_at": None,
            "review_status": status,
            "annotation_version": "1",
            "guide_version": "1",
        },
        "verified_empty": verified_empty,
        "unusable": unusable,
        "annotations": annotations,
    }


POLY = {"type": "polygon", "polygon": [10, 10, 30, 10, 30, 30, 10, 30]}
BOX = {"type": "bbox", "bbox": [40, 40, 20, 20]}


class DetectLine(unittest.TestCase):
    def test_normalisation_is_center_xywh(self):
        # box [40,40,20,20] in 100x100 -> center (50,50), size (20,20)
        self.assertEqual(
            detect_line(1, [40, 40, 20, 20], 100, 100),
            "1 0.500000 0.500000 0.200000 0.200000",
        )

    def test_degenerate_box_returns_none(self):
        self.assertIsNone(detect_line(0, [10, 10, 0, 5], 100, 100))


class Gating(unittest.TestCase):
    def _lines(self, record, include_unreviewed=False, classes=DEFAULT_CLASSES):
        drops = {}
        class_index = {n: i for i, n in enumerate(classes)}
        return (
            record_label_lines(
                record,
                class_index=class_index,
                task="detect",
                include_unreviewed=include_unreviewed,
                drops=drops,
            ),
            drops,
        )

    def test_unreviewed_is_skipped_by_default(self):
        (lines, split), _ = self._lines(
            _record("p1", "train", "unreviewed", [_obj("weed_target", BOX)])
        )
        self.assertIsNone(lines)
        self.assertIsNone(split)

    def test_accepted_is_exported(self):
        (lines, split), _ = self._lines(
            _record("t1", "train", "accepted", [_obj("weed_target", BOX)])
        )
        self.assertEqual(split, "train")
        self.assertEqual(len(lines), 1)

    def test_deleted_object_is_dropped(self):
        (lines, _split), drops = self._lines(
            _record(
                "t1",
                "train",
                "accepted",
                [
                    _obj("weed_target", BOX),
                    _obj("weed_target", BOX, edit="deleted"),
                ],
            )
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(drops["deleted_object"], 1)

    def test_unusable_never_exported(self):
        (lines, split), drops = self._lines(_record("u1", "train", "in_review", [], unusable=True))
        self.assertIsNone(lines)
        self.assertEqual(drops["unusable"], 1)

    def test_unassigned_split_excluded(self):
        (lines, _split), drops = self._lines(
            _record("x1", "unassigned", "accepted", [_obj("weed_target", BOX)])
        )
        self.assertIsNone(lines)
        self.assertEqual(drops["split_excluded='unassigned'"], 1)

    def test_label_outside_reduced_class_map_is_dropped(self):
        (lines, _split), drops = self._lines(
            _record(
                "t1",
                "train",
                "accepted",
                [
                    _obj("rice_protect", POLY),
                    _obj("weed_target", BOX),
                ],
            ),
            classes=("weed_target",),  # rice not in the map
        )
        self.assertEqual(len(lines), 1)  # only weed kept
        self.assertEqual(drops["label_not_in_class_map='rice_protect'"], 1)

    def test_verified_empty_accepted_is_a_negative_not_a_skip(self):
        (lines, split), _ = self._lines(_record("s1", "test", "accepted", [], verified_empty=True))
        self.assertEqual(split, "test")
        self.assertEqual(lines, [])  # empty label = background negative


class SegmentGeometry(unittest.TestCase):
    def test_box_only_is_not_fabricated_into_a_mask(self):
        drops = {}
        class_index = {n: i for i, n in enumerate(DEFAULT_CLASSES)}
        lines, _split = record_label_lines(
            _record(
                "t1",
                "train",
                "accepted",
                [
                    _obj("rice_protect", POLY),
                    _obj("weed_target", BOX),
                ],
            ),
            class_index=class_index,
            task="segment",
            include_unreviewed=False,
            drops=drops,
        )
        self.assertEqual(len(lines), 1)  # only the polygon
        self.assertEqual(drops["bbox_only_in_segment_mode"], 1)


class EndToEnd(unittest.TestCase):
    def test_include_unreviewed_stamps_marker(self):
        records = [
            _record("t1", "train", "accepted", [_obj("weed_target", BOX)]),
            _record("p1", "train", "unreviewed", [_obj("weed_target", BOX)]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pkg = tmp / "pkg.jsonl"
            pkg.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

            truth = tmp / "truth"
            rep = export(
                packages=[pkg],
                out_root=truth,
                images_root=None,
                task="detect",
                classes=list(DEFAULT_CLASSES),
                include_unreviewed=False,
                link="none",
            )
            self.assertEqual(rep["per_split"]["train"]["images"], 1)
            self.assertFalse((truth / "UNREVIEWED_DO_NOT_TRAIN.txt").exists())

            loose = tmp / "loose"
            rep2 = export(
                packages=[pkg],
                out_root=loose,
                images_root=None,
                task="detect",
                classes=list(DEFAULT_CLASSES),
                include_unreviewed=True,
                link="none",
            )
            self.assertEqual(rep2["per_split"]["train"]["images"], 2)
            self.assertTrue((loose / "UNREVIEWED_DO_NOT_TRAIN.txt").is_file())
            self.assertTrue(rep2["gating"].startswith("UNREVIEWED"))


if __name__ == "__main__":
    unittest.main()
