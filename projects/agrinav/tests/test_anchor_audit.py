"""Tests for the model-free anchor-coverage audit.

The audit answers a question that would otherwise cost GPU hours: can the anchor
set reach the ground-truth boxes at all? Its arithmetic has to match WeedDet's
``AnchorGenerator`` and ``letterbox_pil`` exactly, or the answer is worthless --
so those two agreements are asserted against the real implementations rather
than against hand-copied constants.
"""

import json
import math

import pytest

from agrinav.data.anchor_audit import (
    DEFAULT_ASPECT_RATIOS,
    DEFAULT_IMG_SIZE,
    DEFAULT_SCALES,
    DEFAULT_STRIDES,
    _centred_iou,
    _grid_iou,
    _ratio_bucket,
    anchor_shapes,
    audit,
    best_iou_for_box,
    letterbox_params,
    main,
)
from agrinav.models import weeddet_v6b as wd


def test_anchor_shapes_match_the_model_anchor_generator():
    """Audit shapes must equal AnchorGenerator's, or coverage numbers are fiction."""
    generator = wd.AnchorGenerator()
    audited = {(round(w, 6), round(h, 6)) for w, h, _ in anchor_shapes()}

    expected = set()
    for stride in generator.strides:
        base = generator.base_scale * stride
        for ratio in generator.aspect_ratios:
            for scale in generator.scales:
                expected.add(
                    (
                        round(base * scale * math.sqrt(ratio), 6),
                        round(base * scale / math.sqrt(ratio), 6),
                    )
                )
    assert audited == expected
    assert len(anchor_shapes()) == len(DEFAULT_STRIDES) * len(DEFAULT_ASPECT_RATIOS) * len(
        DEFAULT_SCALES
    )


def test_no_anchor_is_wider_than_tall():
    """Documents the geometry: aspect ratios are all <= 1, so nothing is wide."""
    assert max(w / h for w, h, _ in anchor_shapes()) == pytest.approx(1.0)


def test_letterbox_params_match_letterbox_pil():
    from PIL import Image

    for width, height in ((640, 480), (100, 700), (512, 512), (1333, 800)):
        image = Image.new("RGB", (width, height))
        _, sx, sy, pad_l, pad_t = wd.letterbox_pil(image, DEFAULT_IMG_SIZE)
        assert letterbox_params(width, height, DEFAULT_IMG_SIZE) == pytest.approx(
            (sx, sy, pad_l, pad_t)
        )


def test_centred_iou_is_one_for_identical_boxes_and_falls_with_mismatch():
    assert _centred_iou(20, 40, 20, 40) == pytest.approx(1.0)
    # Twice the height, same width -> inter 20*40, union 20*40 + 20*80 - 20*40.
    assert _centred_iou(20, 40, 20, 80) == pytest.approx(0.5)
    assert _centred_iou(10, 10, 200, 200) < 0.01


def test_grid_iou_never_exceeds_the_centred_upper_bound():
    shapes = anchor_shapes()
    for cx, cy, w, h in ((100.0, 100.0, 30.0, 60.0), (7.3, 250.9, 12.0, 12.0)):
        shape_iou, grid_iou = best_iou_for_box(cx, cy, w, h, shapes)
        # A box centred exactly on a grid centre makes the two equal, so compare
        # with a tolerance rather than strictly.
        assert 0.0 <= grid_iou <= shape_iou + 1e-9
        assert shape_iou <= 1.0


def test_grid_iou_equals_shape_iou_when_the_box_sits_on_a_grid_centre():
    # stride 4 -> centres at 2, 6, 10, ...; a box centred at 6.0 aligns exactly.
    aligned = _grid_iou(6.0, 6.0, 12.0, 12.0, 12.0, 12.0, stride=4)
    assert aligned == pytest.approx(_centred_iou(12.0, 12.0, 12.0, 12.0))


def test_ratio_bucket_boundaries():
    assert _ratio_bucket(40, 10) == "wide(w/h>=2)"
    assert _ratio_bucket(15, 10) == "slightly_wide(1.2-2)"
    assert _ratio_bucket(10, 10) == "square(0.8-1.2)"
    assert _ratio_bucket(5, 40) == "tall(w/h<0.8)"


def _write_coco(path, boxes):
    """One 512x512 image (letterbox is then the identity) with the given xywh boxes."""
    coco = {
        "categories": [{"id": 1, "name": "rice_protect"}],
        "images": [{"id": 1, "file_name": "a.jpg", "width": 512, "height": 512}],
        "annotations": [
            {"id": i, "image_id": 1, "category_id": 1, "bbox": list(box), "iscrowd": 0}
            for i, box in enumerate(boxes, start=1)
        ],
    }
    path.write_text(json.dumps(coco), encoding="utf-8")
    return str(path)


def test_audit_flags_wide_boxes_as_uncovered(tmp_path):
    """A very wide box is exactly what a tall-only anchor set cannot represent."""
    ann_file = _write_coco(tmp_path / "wide.coco.json", [[100, 240, 300, 20]])
    report = audit(ann_file)

    assert report["n_boxes"] == 1
    assert report["fractions"]["grid_iou<0.5"] == 1.0
    assert report["by_group"]["ratio:wide(w/h>=2)"]["n"] == 1


def test_audit_reports_a_well_matched_box_as_covered(tmp_path):
    """A tall box near an anchor size must clear the 0.5 assignment threshold."""
    ann_file = _write_coco(tmp_path / "tall.coco.json", [[100, 100, 20, 60]])
    report = audit(ann_file)

    assert report["fractions"]["grid_iou<0.5"] == 0.0
    assert report["mean_shape_iou"] > 0.5


def test_audit_applies_the_same_degenerate_box_filter_as_the_dataset(tmp_path):
    """`w > 1 and h > 1` mirrors CocoWeedDataset, so both see the same boxes."""
    ann_file = _write_coco(tmp_path / "mixed.coco.json", [[10, 10, 1, 1], [50, 50, 30, 40]])
    assert audit(ann_file)["n_boxes"] == 1


def test_widening_the_aspect_ratios_recovers_wide_boxes(tmp_path):
    """The audit doubles as the fix check: does adding wide anchors help?"""
    ann_file = _write_coco(tmp_path / "wide.coco.json", [[100, 240, 300, 20]])

    assert audit(ann_file)["fractions"]["grid_iou<0.5"] == 1.0
    widened = audit(ann_file, aspect_ratios=(0.2, 0.33, 0.5, 1.0, 2.0, 4.0, 8.0))
    assert widened["fractions"]["grid_iou<0.5"] == 0.0


def test_cli_writes_a_json_report(tmp_path, capsys):
    ann_file = _write_coco(tmp_path / "cli.coco.json", [[50, 50, 30, 40]])
    out = tmp_path / "nested" / "report.json"

    assert main(["--ann-file", ann_file, "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n_boxes"] == 1
    assert report["anchor_config"]["n_distinct_shapes"] == 36
    assert "anchor audit" in capsys.readouterr().out
