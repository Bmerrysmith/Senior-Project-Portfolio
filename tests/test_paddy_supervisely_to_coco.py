"""Tests for scripts/paddy_supervisely_to_coco.py."""

import unittest

from agrinav.data.paddy_supervisely_to_coco import (
    RICE_PROTECT_ID,
    polygon_area,
    session_of,
    supervisely_objects_to_annotations,
)


class PaddyConverterTests(unittest.TestCase):
    def test_session_grouping_strips_frame(self):
        self.assertEqual(session_of("0804_0002_Frame_15"), "0804_0002")
        self.assertEqual(session_of("0808_0004_Frame_103"), "0808_0004")

    def test_polygon_area_square(self):
        self.assertAlmostEqual(polygon_area([[0, 0], [10, 0], [10, 10], [0, 10]]), 100.0)

    def test_panicle_polygon_becomes_rice_protect(self):
        ann = {
            "objects": [
                {
                    "classTitle": "panicle",
                    "geometryType": "polygon",
                    "points": {"exterior": [[0, 0], [20, 0], [20, 20], [0, 20]], "interior": []},
                }
            ]
        }
        frags = supervisely_objects_to_annotations(ann)
        self.assertEqual(len(frags), 1)
        self.assertEqual(frags[0]["category_id"], RICE_PROTECT_ID)
        self.assertEqual(frags[0]["bbox"], [0.0, 0.0, 20.0, 20.0])
        self.assertAlmostEqual(frags[0]["area"], 400.0)

    def test_non_polygon_and_tiny_are_skipped(self):
        ann = {
            "objects": [
                {"classTitle": "panicle", "geometryType": "bitmap", "points": {"exterior": []}},
                {
                    "classTitle": "panicle",
                    "geometryType": "polygon",
                    "points": {"exterior": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                },  # area 4 < 16
            ]
        }
        self.assertEqual(supervisely_objects_to_annotations(ann, min_area=16), [])


if __name__ == "__main__":
    unittest.main()
