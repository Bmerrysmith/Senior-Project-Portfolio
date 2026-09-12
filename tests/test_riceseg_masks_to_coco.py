"""Tests for scripts/riceseg_masks_to_coco.py (RiceSEG mask -> instance polygons)."""

import unittest

import numpy as np

from agrinav.data.riceseg_masks_to_coco import (
    RICESEG_TO_CANONICAL,
    WEED_CANONICAL_ID,
    mask_to_instances,
    member_country_site,
    source_photo_id,
)


class MaskToInstancesTests(unittest.TestCase):
    def test_rice_and_weed_blobs_become_separate_instances(self):
        mask = np.zeros((64, 64), dtype=np.uint8)
        mask[5:25, 5:25] = 1  # green_rice -> rice_protect
        mask[40:60, 40:60] = 4  # weed -> weed_target
        inst = mask_to_instances(mask, min_area=16)
        cats = sorted(i["category_id"] for i in inst)
        self.assertEqual(cats, [1, WEED_CANONICAL_ID])
        for i in inst:
            self.assertGreaterEqual(len(i["segmentation"][0]), 6)  # >=3 points
            self.assertEqual(len(i["bbox"]), 4)
            self.assertGreater(i["area"], 0)

    def test_rice_subclasses_merge_into_one_instance(self):
        # green_rice + senescent + panicle touching -> one rice_protect blob
        mask = np.zeros((64, 64), dtype=np.uint8)
        mask[10:30, 10:20] = 1
        mask[10:30, 20:30] = 2
        mask[10:30, 30:40] = 3
        inst = mask_to_instances(mask, min_area=16)
        rice = [i for i in inst if i["category_id"] == 1]
        self.assertEqual(len(rice), 1)

    def test_duckweed_maps_to_non_target_aquatic(self):
        mask = np.zeros((32, 32), dtype=np.uint8)
        mask[4:28, 4:28] = 5
        inst = mask_to_instances(mask, min_area=16)
        self.assertEqual([i["category_id"] for i in inst], [4])

    def test_tiny_specks_below_min_area_are_dropped(self):
        mask = np.zeros((32, 32), dtype=np.uint8)
        mask[0:2, 0:2] = 4  # 4 px weed speck
        inst = mask_to_instances(mask, min_area=16)
        self.assertEqual(inst, [])

    def test_background_only_mask_yields_nothing(self):
        self.assertEqual(mask_to_instances(np.zeros((32, 32), np.uint8)), [])


class ProvenanceTests(unittest.TestCase):
    def test_member_country_site_both_shapes(self):
        self.assertEqual(
            member_country_site("global rice segmentation/China/GD/rgb/x.jpg"), ("China", "GD")
        )
        self.assertEqual(
            member_country_site("global rice segmentation/India/rgb/x.jpg"), ("India", None)
        )

    def test_source_photo_id_strips_tile_suffix(self):
        self.assertEqual(source_photo_id("IMG_5014_subset_overlap_0_4"), "IMG_5014")
        self.assertEqual(source_photo_id("DSC0001"), "DSC0001")

    def test_class_map_covers_all_semantic_values(self):
        self.assertEqual(set(RICESEG_TO_CANONICAL), {1, 2, 3, 4, 5})


if __name__ == "__main__":
    unittest.main()
