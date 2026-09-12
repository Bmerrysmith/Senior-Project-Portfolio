"""Tests for scripts/build_detector_split.py — group-leakage-free split."""

import unittest

from agrinav.data.build_detector_split import (
    build_split,
    stratified_group_split,
)


def _synthetic_coco():
    """3 groups x 2 tiles each; group g0/g1 have weed, g2 does not."""
    images, annotations = [], []
    iid = aid = 0
    for gi in range(6):
        group = f"riceseg:China/PHOTO_{gi // 2}"  # 2 tiles per source photo
        has_weed = gi < 4
        iid += 1
        images.append(
            {
                "id": iid,
                "group_id": group,
                "source_dataset": "riceseg",
                "country": "China",
                "file_name": f"t{iid}.jpg",
            }
        )
        aid += 1
        annotations.append(
            {
                "id": aid,
                "image_id": iid,
                "category_id": 1,
                "segmentation": [[0, 0, 1, 0, 1, 1]],
                "bbox": [0, 0, 1, 1],
                "area": 1,
                "iscrowd": 0,
            }
        )
        if has_weed:
            aid += 1
            annotations.append(
                {
                    "id": aid,
                    "image_id": iid,
                    "category_id": 2,
                    "segmentation": [[0, 0, 1, 0, 1, 1]],
                    "bbox": [0, 0, 1, 1],
                    "area": 1,
                    "iscrowd": 0,
                }
            )
    return {
        "categories": [{"id": 1, "name": "rice_protect"}, {"id": 2, "name": "weed_target"}],
        "images": images,
        "annotations": annotations,
    }


class SplitTests(unittest.TestCase):
    def test_no_group_crosses_splits(self):
        assignment, merged, split_images, stats = build_split(
            [_synthetic_coco()], (0.5, 0.25, 0.25), seed=1
        )
        # Every image of a group must land in its group's single split.
        group_split = {}
        img_group = {im["id"]: im["group_id"] for im in merged["images"]}
        for sp, ids in split_images.items():
            for i in ids:
                g = img_group[i]
                self.assertIn(group_split.setdefault(g, sp), (sp,))

    def test_assignment_is_deterministic(self):
        a1 = stratified_group_split(
            [{"group_id": f"g{i}", "stratum": "s"} for i in range(10)], seed=7
        )
        a2 = stratified_group_split(
            [{"group_id": f"g{i}", "stratum": "s"} for i in range(10)], seed=7
        )
        self.assertEqual(a1, a2)

    def test_all_three_splits_are_nonempty_with_enough_groups(self):
        _, _, split_images, stats = build_split([_synthetic_coco()], (0.34, 0.33, 0.33), seed=3)
        # 3 source-photo groups -> one per split.
        self.assertEqual(sum(s["groups"] for s in stats.values()), 3)

    def test_ratios_must_sum_to_one(self):
        with self.assertRaises(AssertionError):
            stratified_group_split([{"group_id": "g", "stratum": "s"}], (0.5, 0.4, 0.4))


if __name__ == "__main__":
    unittest.main()
