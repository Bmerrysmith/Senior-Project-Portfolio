"""Tests for the phase-2 curated-RICE dataset rebuild.

The defects this module exists to prevent are all *silent*: an image assigned to
the wrong split, an annotation that no longer matches its pixels, a box quietly
dropped. So these tests assert on the observable consequences (membership,
dimensions, hashes, rejection records) rather than on internal calls.
"""

from __future__ import annotations

import io
import json
import os
import zipfile

import pytest
from PIL import Image

from agrinav.data.build_rice_phase2 import (
    BuildError,
    build,
    derive_group_id,
    normalize_image_bytes,
    package,
    preflight,
    sanitize_box,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Fixture construction
# --------------------------------------------------------------------------- #
def _jpeg(
    width: int, height: int, *, orientation: int | None = None, colour=(20, 120, 40)
) -> bytes:
    """Encode a solid-colour JPEG, optionally tagging an EXIF orientation."""
    image = Image.new("RGB", (width, height), colour)
    buffer = io.BytesIO()
    if orientation is None:
        image.save(buffer, format="JPEG", quality=95)
    else:
        exif = image.getexif()
        exif[274] = orientation
        image.save(buffer, format="JPEG", quality=95, exif=exif.tobytes())
    return buffer.getvalue()


def _write_source(root, images_by_split, boxes_by_name):
    """Lay out a miniature copy of the deliverable's detection/RICE tree.

    Args:
        root: destination directory.
        images_by_split: ``{native_split: [(file_name, raw_bytes, coco_w, coco_h)]}``.
        boxes_by_name: ``{file_name: [(category_id, [x, y, w, h])]}``.
    """
    os.makedirs(os.path.join(root, "annotations"), exist_ok=True)
    for split in ("train", "valid", "test"):
        directory = os.path.join(root, "images", split)
        os.makedirs(directory, exist_ok=True)
        images, annotations = [], []
        for index, (name, raw, width, height) in enumerate(images_by_split.get(split, []), start=1):
            with open(os.path.join(directory, name), "wb") as handle:
                handle.write(raw)
            images.append({"id": index, "file_name": name, "width": width, "height": height})
            for category_id, bbox in boxes_by_name.get(name, []):
                annotations.append(
                    {
                        "id": len(annotations) + 1,
                        "image_id": index,
                        "category_id": category_id,
                        "bbox": list(bbox),
                        "area": bbox[2] * bbox[3],
                        "iscrowd": 0,
                        "segmentation": [[0, 0, 1, 0, 1, 1]],
                    }
                )
        doc = {
            "images": images,
            "annotations": annotations,
            "categories": [
                {"id": 1, "name": "rice_protect"},
                {"id": 2, "name": "weed_target"},
            ],
        }
        with open(
            os.path.join(root, "annotations", f"instances_{split}.coco.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(doc, handle)


def _write_manifest(root, assignment, per_split=None):
    payload = {
        "method": "test fixture",
        "block_size": 40,
        "filename_split": assignment,
    }
    if per_split is not None:
        payload["per_split"] = per_split
    path = os.path.join(root, "grouped_split.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


@pytest.fixture
def source_tree(tmp_path):
    """A 6-image source whose folder layout disagrees with its grouped manifest.

    Mirrors the real defect: the intended split and the native folder differ for
    most files, one image carries EXIF orientation 8 (so its stored pixels are
    transposed relative to its COCO record), and two boxes are outside bounds --
    one by a hair (clip) and one badly (reject).
    """
    root = tmp_path / "source"
    rotated = _jpeg(40, 20, orientation=8)  # stored 40x20, displays as 20x40
    # Distinct colours per image: the preflight treats byte-identical images as a
    # defect, so a fixture must not accidentally produce duplicates.
    images_by_split = {
        "train": [
            ("frame_000000_jpg.rf.aaaa.jpg", _jpeg(32, 24, colour=(10, 100, 30)), 32, 24),
            ("frame_000001_jpg.rf.bbbb.jpg", _jpeg(32, 24, colour=(20, 110, 40)), 32, 24),
            ("frame_000100_jpg.rf.cccc.jpg", rotated, 20, 40),
        ],
        "valid": [
            ("frame_000101_jpg.rf.dddd.jpg", _jpeg(32, 24, colour=(30, 120, 50)), 32, 24),
            ("frame_000200_jpg.rf.eeee.jpg", _jpeg(32, 24, colour=(9, 9, 9)), 32, 24),
        ],
        "test": [("frame_000201_jpg.rf.ffff.jpg", _jpeg(32, 24, colour=(1, 2, 3)), 32, 24)],
    }
    boxes_by_name = {
        "frame_000000_jpg.rf.aaaa.jpg": [(1, [1, 1, 10, 10]), (2, [4, 4, 6, 6])],
        "frame_000001_jpg.rf.bbbb.jpg": [(1, [0, 0, 32.5, 24.0])],  # 0.5 px over -> clip
        "frame_000100_jpg.rf.cccc.jpg": [(1, [2, 2, 15, 30])],  # valid only in 20x40
        "frame_000101_jpg.rf.dddd.jpg": [(1, [5, 5, 5, 5]), (2, [60, 5, 10, 10])],  # 2nd rejected
        "frame_000200_jpg.rf.eeee.jpg": [(2, [3, 3, 8, 8])],
        "frame_000201_jpg.rf.ffff.jpg": [(1, [6, 6, 9, 9])],
    }
    _write_source(root, images_by_split, boxes_by_name)
    # Intended assignment deliberately cuts across the native folders.
    assignment = {
        "frame_000000_jpg.rf.aaaa.jpg": "train",
        "frame_000001_jpg.rf.bbbb.jpg": "train",
        "frame_000100_jpg.rf.cccc.jpg": "valid",
        "frame_000101_jpg.rf.dddd.jpg": "train",
        "frame_000200_jpg.rf.eeee.jpg": "test",
        "frame_000201_jpg.rf.ffff.jpg": "valid",
    }
    manifest = _write_manifest(
        root,
        assignment,
        per_split={
            "train": {"images": 3, "rice": 3, "weed": 2},
            "valid": {"images": 2, "rice": 2, "weed": 0},
            "test": {"images": 1, "rice": 0, "weed": 1},
        },
    )
    return {"root": str(root), "manifest": manifest, "assignment": assignment}


# --------------------------------------------------------------------------- #
# Unit-level rules
# --------------------------------------------------------------------------- #
def test_group_id_buckets_contiguous_frames_together():
    assert derive_group_id("frame_000000_jpg.rf.x.jpg") == derive_group_id(
        "frame_000039_jpg.rf.y.jpg"
    )
    assert derive_group_id("frame_000039_jpg.rf.y.jpg") != derive_group_id(
        "frame_000040_jpg.rf.z.jpg"
    )


def test_group_id_separates_capture_families():
    assert derive_group_id("frame_000000_jpg.rf.x.jpg") != derive_group_id(
        "seedlingCol_04_0000_jpg.rf.x.jpg"
    )


def test_group_id_handles_parenthesised_and_unnumbered_stems():
    assert derive_group_id("1a_image (101)_jpg.rf.x.jpg").endswith("#2")
    assert derive_group_id("weird-name_jpg.rf.x.jpg").endswith("#na")


@pytest.mark.parametrize(
    ("bbox", "expected_action"),
    [
        ([1, 1, 10, 10], "keep"),
        ([0, 0, 32.5, 24.0], "clip"),  # 0.5 px excursion
        ([-0.5, 0, 10, 10], "clip"),
        ([60, 5, 10, 10], "reject"),  # far outside
        ([5, 5, 0, 5], "reject"),  # zero width
        ([5, 5, -3, 5], "reject"),  # negative width
        ([31.8, 5, 0.1, 5], "reject"),  # survives clipping but < 1 px
    ],
)
def test_sanitize_box_actions(bbox, expected_action):
    assert sanitize_box(bbox, 32, 24).action == expected_action


def test_sanitize_box_clip_stays_inside_bounds():
    decision = sanitize_box([-2.0, -0.5, 12, 12], 32, 24, tolerance=3.0)
    x, y, w, h = decision.bbox
    assert decision.action == "clip"
    assert x >= 0 and y >= 0 and x + w <= 32 and y + h <= 24


def test_sanitize_box_rejects_nonfinite():
    assert sanitize_box([float("nan"), 0, 5, 5], 32, 24).action == "reject"
    assert sanitize_box([0, 0, float("inf"), 5], 32, 24).action == "reject"


def test_normalize_leaves_unoriented_bytes_untouched():
    raw = _jpeg(32, 24)
    data, width, height, reoriented = normalize_image_bytes(raw)
    assert data is raw and (width, height) == (32, 24) and reoriented is False


def test_normalize_applies_orientation_and_strips_the_tag():
    raw = _jpeg(40, 20, orientation=8)
    data, width, height, reoriented = normalize_image_bytes(raw)
    assert reoriented is True
    assert (width, height) == (20, 40)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (20, 40)
        assert image.getexif().get(274) in (None, 1)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def test_build_assigns_by_manifest_not_by_source_folder(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    for name, split in source_tree["assignment"].items():
        assert (out / "images" / split / name).is_file(), f"{name} not in {split}"
        for other in ("train", "valid", "test"):
            if other != split:
                assert not (out / "images" / other / name).exists()


def test_build_reconciles_rotated_image_dimensions(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    doc = json.loads((out / "annotations" / "instances_valid.coco.json").read_text())
    record = next(r for r in doc["images"] if r["file_name"].startswith("frame_000100"))
    assert (record["width"], record["height"]) == (20, 40)
    assert record["exif_reoriented"] is True
    with Image.open(out / "images" / "valid" / record["file_name"]) as image:
        assert image.size == (20, 40)


def test_build_records_hashes_and_group_ids(source_tree, tmp_path):
    out = tmp_path / "out"
    report = build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    membership = json.loads((out / "manifests" / "split_membership.json").read_text())
    assert len(membership) == 6
    assert all(len(entry["sha256"]) == 64 for entry in membership.values())
    assert all(entry["group_id"] for entry in membership.values())
    provenance = json.loads((out / "manifests" / "provenance.json").read_text())
    assert set(provenance["json_sha256"]) >= {
        "annotations/instances_train.coco.json",
        "annotations/instances_valid.coco.json",
        "annotations/instances_test.coco.json",
    }
    assert report["totals"]["images"] == 6
    assert report["totals"]["exif_reoriented"] == 1


def test_build_reports_rejected_and_clipped_boxes(source_tree, tmp_path):
    out = tmp_path / "out"
    report = build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    rejects = json.loads((out / "reports" / "rejected_annotations.json").read_text())
    assert report["totals"]["annotations_rejected"] == 1
    assert report["totals"]["annotations_clipped"] == 1
    assert rejects["counts"]["rejected_by_reason"] == {"out_of_bounds": 1}
    assert rejects["rejected"][0]["file_name"].startswith("frame_000101")
    # The clipped box is emitted, inside bounds.
    doc = json.loads((out / "annotations" / "instances_train.coco.json").read_text())
    dims = {r["id"]: (r["width"], r["height"]) for r in doc["images"]}
    for ann in doc["annotations"]:
        width, height = dims[ann["image_id"]]
        x, y, w, h = ann["bbox"]
        assert x >= 0 and y >= 0 and x + w <= width and y + h <= height


def test_build_drops_unreviewed_segmentation_by_default(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    doc = json.loads((out / "annotations" / "instances_train.coco.json").read_text())
    assert all("segmentation" not in ann for ann in doc["annotations"])
    assert doc["info"]["segmentation_dropped"] is True


def test_build_keeps_segmentation_when_asked(source_tree, tmp_path):
    out = tmp_path / "out"
    build(
        source_tree["root"],
        str(out),
        split_manifest=source_tree["manifest"],
        keep_segmentation=True,
    )
    doc = json.loads((out / "annotations" / "instances_train.coco.json").read_text())
    assert any("segmentation" in ann for ann in doc["annotations"])


def test_build_writes_the_test_split_usage_notice(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    text = (out / "TEST_SPLIT_STATUS.md").read_text(encoding="utf-8")
    assert "may never be evaluated on this split" in text
    assert "trained from scratch" in text
    provenance = json.loads((out / "manifests" / "provenance.json").read_text())
    assert "2026-07-28 checkpoints" in provenance["test_split_status"]


def test_build_flags_images_the_legacy_archive_trained_on(source_tree, tmp_path):
    legacy = tmp_path / "legacy.zip"
    with zipfile.ZipFile(legacy, "w") as archive:
        archive.writestr("images/train/frame_000000_jpg.rf.aaaa.jpg", b"x")
        archive.writestr("images/valid/frame_000200_jpg.rf.eeee.jpg", b"x")
    out = tmp_path / "out"
    build(
        source_tree["root"],
        str(out),
        split_manifest=source_tree["manifest"],
        legacy_archive=str(legacy),
    )
    membership = json.loads((out / "manifests" / "split_membership.json").read_text())
    assert membership["frame_000000_jpg.rf.aaaa.jpg"]["trained_on_legacy"] is True
    assert membership["frame_000200_jpg.rf.eeee.jpg"]["trained_on_legacy"] is False
    assert membership["frame_000201_jpg.rf.ffff.jpg"]["trained_on_legacy"] is False


def test_build_fails_when_a_manifest_image_is_missing_from_source(source_tree, tmp_path):
    assignment = dict(source_tree["assignment"])
    assignment["frame_000999_jpg.rf.zzzz.jpg"] = "train"
    path = os.path.join(source_tree["root"], "incomplete_split.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"method": "t", "filename_split": assignment}, handle)
    with pytest.raises(BuildError, match="absent from"):
        build(source_tree["root"], str(tmp_path / "out"), split_manifest=path)


def test_build_fails_when_a_source_image_is_unassigned(source_tree, tmp_path):
    assignment = dict(source_tree["assignment"])
    assignment.pop("frame_000201_jpg.rf.ffff.jpg")
    path = os.path.join(source_tree["root"], "partial_split.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"method": "t", "filename_split": assignment}, handle)
    with pytest.raises(BuildError, match="not assigned"):
        build(source_tree["root"], str(tmp_path / "out"), split_manifest=path)


def test_build_fails_when_manifest_counts_disagree_with_source(source_tree, tmp_path):
    path = os.path.join(source_tree["root"], "wrong_counts.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "method": "t",
                "filename_split": source_tree["assignment"],
                "per_split": {"train": {"images": 99, "rice": 3, "weed": 2}},
            },
            handle,
        )
    with pytest.raises(BuildError, match="train.images: manifest 99"):
        build(source_tree["root"], str(tmp_path / "out"), split_manifest=path)


def test_build_refuses_a_nonempty_out_root(source_tree, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("previous build")
    with pytest.raises(BuildError, match="not empty"):
        build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"], overwrite=True)


def test_build_fails_when_coco_dimensions_cannot_be_reconciled(tmp_path):
    root = tmp_path / "source"
    _write_source(
        root,
        {"train": [("frame_000000_jpg.rf.aaaa.jpg", _jpeg(32, 24), 99, 99)]},
        {},
    )
    manifest = _write_manifest(root, {"frame_000000_jpg.rf.aaaa.jpg": "train"})
    with pytest.raises(BuildError, match="normalized pixels are 32x24"):
        build(str(root), str(tmp_path / "out"), split_manifest=manifest)


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #
def test_preflight_passes_on_a_clean_build(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    report = preflight(str(out), split_manifest=source_tree["manifest"])
    assert report["passed"] is True
    assert report["manifest_check"]["assignment_mismatches"] == 0
    assert report["counts"]["train"]["images"] == 3
    assert (out / "reports" / "preflight.json").is_file()


def test_preflight_is_self_contained_via_the_vendored_manifest(source_tree, tmp_path):
    """A consumer must be able to verify the tree without the build machine's paths."""
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    assert (out / "manifests" / "grouped_split.json").is_file()
    # Break the recorded absolute path; the vendored copy must still be found.
    provenance_path = out / "manifests" / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["split_manifest"] = "/nonexistent/grouped_split.json"
    provenance_path.write_text(json.dumps(provenance))
    report = preflight(str(out))
    assert report["passed"] is True
    assert report["manifest_check"]["checked"] is True
    assert report["manifest_check"]["assignment_mismatches"] == 0


def test_preflight_catches_a_tampered_image(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    target = out / "images" / "train" / "frame_000000_jpg.rf.aaaa.jpg"
    target.write_bytes(_jpeg(32, 24, colour=(200, 10, 10)))
    with pytest.raises(BuildError, match="hash_mismatch"):
        preflight(str(out), split_manifest=source_tree["manifest"])


def test_preflight_catches_a_moved_image(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    name = "frame_000000_jpg.rf.aaaa.jpg"
    (out / "images" / "train" / name).rename(out / "images" / "valid" / name)
    with pytest.raises(BuildError, match="image_missing"):
        preflight(str(out), split_manifest=source_tree["manifest"])


def test_preflight_catches_an_assignment_edit(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    path = os.path.join(source_tree["root"], "edited_split.json")
    edited = dict(source_tree["assignment"])
    edited["frame_000000_jpg.rf.aaaa.jpg"] = "test"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"method": "t", "filename_split": edited}, handle)
    with pytest.raises(BuildError, match="assignment_mismatch"):
        preflight(str(out), split_manifest=path)


def test_preflight_catches_an_out_of_bounds_annotation(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    path = out / "annotations" / "instances_train.coco.json"
    doc = json.loads(path.read_text())
    doc["annotations"][0]["bbox"] = [1000, 1000, 10, 10]
    path.write_text(json.dumps(doc))
    with pytest.raises(BuildError, match="out_of_bounds_box"):
        preflight(str(out), split_manifest=source_tree["manifest"])


# --------------------------------------------------------------------------- #
# Packaging
# --------------------------------------------------------------------------- #
def test_package_excludes_the_burned_test_split_by_default(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    result = package(str(out), str(tmp_path / "ds.zip"))
    with zipfile.ZipFile(tmp_path / "ds.zip") as archive:
        names = archive.namelist()
    assert not any(name.startswith("images/test/") for name in names)
    assert not any("instances_test" in name for name in names)
    assert any(name.startswith("images/train/") for name in names)
    assert len(result["sha256"]) == 64
    assert result["includes_test"] is False


def test_preflight_passes_on_an_extracted_training_archive(source_tree, tmp_path):
    """The packaged archive omits test, and the consumer-side gate must accept that."""
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    package(str(out), str(tmp_path / "ds.zip"))
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(tmp_path / "ds.zip") as archive:
        archive.extractall(extracted)
    report = preflight(str(extracted))
    assert report["passed"] is True
    assert report["splits_present"] == ["train", "valid"]
    assert report["manifest_check"]["splits_absent"] == ["test"]
    assert report["manifest_check"]["manifest_images_not_emitted"] == 0


def test_preflight_rejects_images_with_no_annotations_file(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    (out / "annotations" / "instances_test.coco.json").unlink()
    with pytest.raises(BuildError, match="images_without_annotations"):
        preflight(str(out))


def test_preflight_rejects_a_directory_that_is_not_a_build(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(BuildError, match="not a build produced by this module"):
        preflight(str(empty))


def test_package_can_include_the_test_split(source_tree, tmp_path):
    out = tmp_path / "out"
    build(source_tree["root"], str(out), split_manifest=source_tree["manifest"])
    package(str(out), str(tmp_path / "full.zip"), include_test=True)
    with zipfile.ZipFile(tmp_path / "full.zip") as archive:
        assert any(name.startswith("images/test/") for name in archive.namelist())
