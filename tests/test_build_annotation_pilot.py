import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from agrinav.data.build_annotation_pilot import (
    PilotBuildError,
    annotation_record_stub,
    build_manifest,
    detector_capture_family,
    inventory_coco,
    inventory_riceseg,
    load_pilot_config,
    materialize_selected_media,
    select_annotation_pilot,
    sha256_file,
    write_annotation_stubs,
)
from agrinav.data.validate_annotation_package import validate_packages


def png_bytes(value: int, size: tuple[int, int] = (8, 8), mode: str = "L") -> bytes:
    output = BytesIO()
    Image.new(mode, size, value).save(output, format="PNG")
    return output.getvalue()


def rgb_bytes(
    size: tuple[int, int] = (8, 8),
    color: tuple[int, int, int] = (10, 120, 20),
) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


class AnnotationPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.riceseg_zip = root / "RiceSEG.zip"
        self.coco_zip = root / "detector.zip"
        self._make_riceseg_zip()
        self._make_coco_zip()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _make_riceseg_zip(self) -> None:
        tiles = [
            ("China/GD", "IMG_1_subset_overlap_0_0", 4),
            ("China/GD", "IMG_1_subset_overlap_0_1", 1),
            ("China/GX", "IMG_2_subset_overlap_0_0", 5),
            ("India", "DSC00278_subset_overlap_0_0", 4),
            ("Philippines", "PH_7_subset_overlap_1_0", 2),
            ("Japan/TKO_1", "JP_9_subset_overlap_1_1", 3),
        ]
        with zipfile.ZipFile(self.riceseg_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, (location, stem, mask_value) in enumerate(tiles):
                prefix = f"global rice segmentation/{location}"
                archive.writestr(
                    f"{prefix}/rgb/{stem}.png",
                    rgb_bytes(color=(10 + index, 120, 20)),
                )
                archive.writestr(f"{prefix}/label/{stem}.png", png_bytes(mask_value))

    def _make_coco_zip(self) -> None:
        filenames = [
            "1a_image-1-_jpg.rf.aaaaaaaa.jpg",
            "1b_image-2-_jpg.rf.bbbbbbbb.jpg",
            "2_3_jpg.rf.cccccccc.jpg",
            "frame_0004_png_jpg.rf.dddddddd.jpg",
            "seedlingCol_03_0005_jpg.rf.eeeeeeee.jpg",
            "seedlingCol_04_0006_jpg.rf.ffffffff.jpg",
            "weeds_seq_0007_jpg.rf.11111111.jpg",
            "00008_jpg.rf.22222222.jpg",
        ]
        images = [
            {"id": index, "file_name": name, "width": 8, "height": 8}
            for index, name in enumerate(filenames, start=1)
        ]
        annotations = []
        annotation_id = 1
        for image in images:
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image["id"],
                    "category_id": 1,
                    "bbox": [0, 0, 4, 4],
                    "area": 16,
                    "iscrowd": 0,
                }
            )
            annotation_id += 1
            if image["id"] in {1, 2, 7, 8}:
                annotations.append(
                    {
                        "id": annotation_id,
                        "image_id": image["id"],
                        "category_id": 2,
                        "bbox": [4, 4, 2, 2],
                        "area": 4,
                        "iscrowd": 0,
                    }
                )
                annotation_id += 1
        document = {
            "images": images,
            "annotations": annotations,
            "categories": [
                {"id": 0, "name": "rice_detection_for_export"},
                {"id": 1, "name": "rice"},
                {"id": 2, "name": "weed"},
            ],
        }
        with zipfile.ZipFile(self.coco_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("train/_annotations.coco.json", json.dumps(document))
            for index, filename in enumerate(filenames):
                archive.writestr(
                    f"train/{filename}",
                    rgb_bytes(color=(100 + index, 120, 20)),
                )

    def test_riceseg_grouping_and_mask_counts(self) -> None:
        records, summary = inventory_riceseg(self.riceseg_zip)
        self.assertEqual(6, summary["image_count"])
        self.assertEqual(5, summary["source_group_count"])
        self.assertEqual(2 * 64, summary["class_pixel_counts"]["weed"])
        image_1_tiles = [record for record in records if record["source_photo_id"] == "IMG_1"]
        self.assertEqual(2, len(image_1_tiles))
        self.assertEqual(1, len({record["group_id"] for record in image_1_tiles}))
        india = next(record for record in records if record["country"] == "India")
        self.assertIsNone(india["site_id"])
        self.assertIn("unreported_site", india["group_id"])

    def test_detector_capture_families_and_inventory(self) -> None:
        records, summary = inventory_coco(self.coco_zip)
        self.assertEqual(8, summary["image_count"])
        self.assertEqual(8, summary["validated_image_count"])
        self.assertEqual(4, summary["weed_positive_image_count"])
        self.assertEqual("1a_image", detector_capture_family("1a_image-8-_jpg.rf.abc.jpg")[0])
        self.assertEqual("2_series", detector_capture_family("2_94_jpg.rf.abc.jpg")[0])
        self.assertEqual("numeric_unresolved", detector_capture_family("00178_jpg.rf.abc.jpg")[0])
        self.assertEqual(
            {
                "1a_image",
                "1b_image",
                "2_series",
                "frame",
                "seedlingCol_03",
                "seedlingCol_04",
                "weeds_seq",
                "numeric_unresolved",
            },
            {record["capture_family"] for record in records},
        )

    def test_source_geometry_and_media_dimensions_are_validated(self) -> None:
        bad_coco = Path(self.temporary.name) / "bad_detector.zip"
        document = {
            "images": [{"id": 1, "file_name": "bad.png", "width": 8, "height": 8}],
            "annotations": [
                {
                    "id": 1,
                    "image_id": 1,
                    "category_id": 1,
                    "bbox": [7, 7, 2, 2],
                }
            ],
            "categories": [{"id": 1, "name": "weed"}],
        }
        with zipfile.ZipFile(bad_coco, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("train/_annotations.coco.json", json.dumps(document))
            archive.writestr("train/bad.png", rgb_bytes())
        with self.assertRaisesRegex(PilotBuildError, "outside image"):
            inventory_coco(bad_coco)

        bad_rice = Path(self.temporary.name) / "bad_riceseg.zip"
        prefix = "global rice segmentation/India"
        with zipfile.ZipFile(bad_rice, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{prefix}/rgb/sample_subset_overlap_0_0.png", rgb_bytes((9, 8)))
            archive.writestr(f"{prefix}/label/sample_subset_overlap_0_0.png", png_bytes(4))
        with self.assertRaisesRegex(PilotBuildError, "size mismatch"):
            inventory_riceseg(bad_rice)

    def test_selection_is_deterministic_unique_and_review_only(self) -> None:
        rice, _ = inventory_riceseg(self.riceseg_zip)
        coco, _ = inventory_coco(self.coco_zip)
        first = select_annotation_pilot(
            rice,
            coco,
            target_size=8,
            seed=77,
            enforce_public_range=False,
        )
        second = select_annotation_pilot(
            rice,
            coco,
            target_size=8,
            seed=77,
            enforce_public_range=False,
        )
        self.assertEqual(first, second)
        self.assertEqual(8, len(first))
        self.assertEqual(8, len({record["sample_id"] for record in first}))
        self.assertEqual(4, sum(record["source_dataset"] == "RiceSEG" for record in first))
        self.assertEqual(
            4,
            sum(record["source_dataset"] == "rice_detection_for_export" for record in first),
        )
        selected_rice = [record for record in first if record["source_dataset"] == "RiceSEG"]
        self.assertEqual(
            len(selected_rice),
            len({record["group_id"] for record in selected_rice}),
        )
        self.assertGreaterEqual(sum(record["proposal_weed_positive"] for record in first), 4)
        for record in first:
            self.assertTrue(record["proposal_only"])
            self.assertEqual("pending_human_review", record["review_status"])
            self.assertIsNone(record["verified_empty"])
            self.assertIsNone(record["positive_weeds"])
            self.assertFalse(record["eligible_for_training"])
            self.assertFalse(record["eligible_for_evaluation"])

    def test_manifest_is_deterministic_and_materializes_only_selected_media(self) -> None:
        first = build_manifest(
            riceseg_zip=self.riceseg_zip,
            coco_zip=self.coco_zip,
            target_size=6,
            gold_size=2,
            seed=99,
            enforce_public_range=False,
        )
        second = build_manifest(
            riceseg_zip=self.riceseg_zip,
            coco_zip=self.coco_zip,
            target_size=6,
            gold_size=2,
            seed=99,
            enforce_public_range=False,
        )
        self.assertEqual(first, second)
        self.assertEqual(2, first["selection"]["gold_subset"]["size"])
        self.assertEqual(
            {"RiceSEG": 1, "rice_detection_for_export": 1},
            first["selection"]["gold_subset"]["source_counts"],
        )
        self.assertEqual(2, sum(sample["gold_subset"] for sample in first["samples"]))
        self.assertTrue(
            all(len(sample["source_image_sha256"]) == 64 for sample in first["samples"])
        )
        self.assertGreaterEqual(
            first["selection"]["observed_proposal_only"]["weed_positive_count"],
            4,
        )
        self.assertIsNone(
            first["selection"]["observed_proposal_only"]["verified_negative_or_nonactionable_count"]
        )
        media_dir = Path(self.temporary.name) / "selected"
        materialize_selected_media(
            first["samples"],
            riceseg_zip=self.riceseg_zip,
            coco_zip=self.coco_zip,
            output_dir=media_dir,
        )
        images = list(media_dir.glob("*/images/*"))
        masks = list(media_dir.glob("riceseg/masks/*"))
        rice_count = sum(record["source_dataset"] == "RiceSEG" for record in first["samples"])
        self.assertEqual(6, len(images))
        self.assertEqual(rice_count, len(masks))
        self.assertEqual(6, len({path.name for path in images}))

        intake_path = Path(self.temporary.name) / "annotation_intake.jsonl"
        write_annotation_stubs(first["samples"], intake_path)
        rows = [json.loads(line) for line in intake_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(6, len(rows))
        self.assertTrue(all(row["verified_empty"] is None for row in rows))
        self.assertTrue(all(row["source"]["split"] == "unassigned" for row in rows))
        self.assertEqual(
            [],
            validate_packages(
                [intake_path],
                ontology_path=Path(__file__).resolve().parents[1] / "data" / "ontology.v1.json",
            ),
        )

    def test_config_loader_and_annotation_stub_keep_unknowns_explicit(self) -> None:
        config_path = Path(self.temporary.name) / "pilot.json"
        config_path.write_text(
            json.dumps(
                {
                    "total_images": 200,
                    "gold_images": 40,
                    "sampling_targets": {"weed_positive_fraction_min": 0.35},
                }
            ),
            encoding="utf-8",
        )
        config = load_pilot_config(config_path)
        self.assertEqual(40, config["gold_images"])

        manifest = build_manifest(
            riceseg_zip=self.riceseg_zip,
            coco_zip=self.coco_zip,
            target_size=4,
            gold_size=2,
            seed=5,
            enforce_public_range=False,
            pilot_config_path=config_path,
        )
        stub = annotation_record_stub(manifest["samples"][0])
        self.assertIsNone(stub["source"]["field_id"])
        self.assertIsNone(stub["source"]["session_id"])
        self.assertIsNone(stub["verified_empty"])
        self.assertEqual("unreviewed", stub["review"]["review_status"])
        self.assertEqual(sha256_file(config_path), manifest["pilot_config"]["sha256"])

    def test_public_cli_size_contract_is_enforced(self) -> None:
        rice, _ = inventory_riceseg(self.riceseg_zip)
        coco, _ = inventory_coco(self.coco_zip)
        with self.assertRaises(PilotBuildError):
            select_annotation_pilot(rice, coco, target_size=149)
        with self.assertRaises(PilotBuildError):
            select_annotation_pilot(rice, coco, target_size=301)


if __name__ == "__main__":
    unittest.main()
