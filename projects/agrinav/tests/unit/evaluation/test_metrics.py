"""CPU-only tests for the decode-agnostic COCO AP metric.

No torch, no detector, no data files -- a tiny synthetic COCO ground truth is
built in memory and scored against hand-made detections. Covers the sanity
anchors an AP implementation must satisfy (perfect -> 1.0, empty -> 0.0,
localisation and per-category behaviour) plus the input-validation guards and the
non-standard-maxDets provenance flag.
"""

import json

import pytest

from agrinav.evaluation.metrics import CocoEvalResult, evaluate_coco_detections, main

# Non-contiguous category ids on purpose ({1, 2, 4}) -- mirrors the real split.
_CATEGORIES = [
    {"id": 1, "name": "rice_protect"},
    {"id": 2, "name": "weed_target"},
    {"id": 4, "name": "non_target_aquatic"},
]


def _gt():
    """Two 100x100 images; image 10 has a cat-1 and a cat-4 box, image 11 a cat-2 box."""
    anns = [
        {
            "id": 1,
            "image_id": 10,
            "category_id": 1,
            "bbox": [10, 10, 20, 20],
            "area": 400,
            "iscrowd": 0,
        },
        {
            "id": 2,
            "image_id": 10,
            "category_id": 4,
            "bbox": [50, 50, 30, 30],
            "area": 900,
            "iscrowd": 0,
        },
        {
            "id": 3,
            "image_id": 11,
            "category_id": 2,
            "bbox": [20, 20, 40, 40],
            "area": 1600,
            "iscrowd": 0,
        },
    ]
    return {
        "images": [
            {"id": 10, "width": 100, "height": 100, "file_name": "a.jpg"},
            {"id": 11, "width": 100, "height": 100, "file_name": "b.jpg"},
        ],
        "categories": _CATEGORIES,
        "annotations": anns,
    }


def _perfect_detections(gt):
    """One detection per GT annotation, identical box, score 1.0."""
    return [
        {
            "image_id": a["image_id"],
            "category_id": a["category_id"],
            "bbox": list(a["bbox"]),
            "score": 1.0,
        }
        for a in gt["annotations"]
    ]


def test_perfect_predictions_score_ap_one():
    gt = _gt()
    result = evaluate_coco_detections(gt, _perfect_detections(gt))
    assert isinstance(result, CocoEvalResult)
    assert result.ap == pytest.approx(1.0, abs=1e-6)
    assert result.ap50 == pytest.approx(1.0, abs=1e-6)
    assert result.ap75 == pytest.approx(1.0, abs=1e-6)
    # every category is perfectly recalled
    for ap in result.per_category_ap.values():
        assert ap == pytest.approx(1.0, abs=1e-6)
    assert result.num_detections == 3
    assert result.num_gt_annotations == 3
    assert result.num_images == 2


def test_empty_predictions_score_zero_without_crashing():
    gt = _gt()
    result = evaluate_coco_detections(gt, [])
    assert result.ap == pytest.approx(0.0, abs=1e-6)
    assert result.ap50 == pytest.approx(0.0, abs=1e-6)
    assert result.num_detections == 0


def test_missing_a_whole_category_zeroes_only_that_category():
    gt = _gt()
    # Drop every cat-2 detection; cats 1 and 4 stay perfect.
    dets = [d for d in _perfect_detections(gt) if d["category_id"] != 2]
    result = evaluate_coco_detections(gt, dets)
    assert result.per_category_ap[1] == pytest.approx(1.0, abs=1e-6)
    assert result.per_category_ap[4] == pytest.approx(1.0, abs=1e-6)
    assert result.per_category_ap[2] == pytest.approx(0.0, abs=1e-6)
    # mean over the three -> ~2/3
    assert result.ap == pytest.approx(2 / 3, abs=1e-3)


def test_localisation_error_drops_ap50():
    gt = _gt()
    dets = _perfect_detections(gt)
    # Shift every box far enough that IoU with its GT falls below 0.5.
    for d in dets:
        d["bbox"][0] += 60
        d["bbox"][1] += 60
    result = evaluate_coco_detections(gt, dets)
    assert result.ap50 == pytest.approx(0.0, abs=1e-6)


def test_category_names_are_carried_through():
    gt = _gt()
    result = evaluate_coco_detections(gt, _perfect_detections(gt))
    assert result.category_names == {1: "rice_protect", 2: "weed_target", 4: "non_target_aquatic"}


def test_nonstandard_maxdets_is_flagged():
    gt = _gt()
    dets = _perfect_detections(gt)
    assert evaluate_coco_detections(gt, dets).is_standard_maxdets is True
    non_std = evaluate_coco_detections(gt, dets, max_dets=300)
    assert non_std.is_standard_maxdets is False
    assert non_std.max_dets == 300
    assert "NON-STANDARD" in non_std.summary()


def test_result_to_dict_is_json_serialisable_with_string_keys():
    gt = _gt()
    result = evaluate_coco_detections(gt, _perfect_detections(gt))
    blob = json.dumps(result.to_dict())  # must not raise
    loaded = json.loads(blob)
    assert loaded["per_category_ap"]["1"] == pytest.approx(1.0, abs=1e-6)
    assert loaded["is_standard_maxdets"] is True


def test_detection_with_unknown_image_id_raises_actionable_error():
    gt = _gt()
    dets = _perfect_detections(gt)
    dets[0]["image_id"] = 999
    with pytest.raises(ValueError, match="image_id=999.*not in the ground-truth"):
        evaluate_coco_detections(gt, dets)


def test_detection_with_unknown_category_id_raises_actionable_error():
    gt = _gt()
    dets = _perfect_detections(gt)
    dets[0]["category_id"] = 3  # 3 is the gap in {1, 2, 4}
    with pytest.raises(ValueError, match="category_id=3.*not a GT category"):
        evaluate_coco_detections(gt, dets)


def test_detection_missing_key_raises():
    gt = _gt()
    dets = _perfect_detections(gt)
    del dets[0]["score"]
    with pytest.raises(ValueError, match="missing key"):
        evaluate_coco_detections(gt, dets)


def test_malformed_bbox_raises():
    gt = _gt()
    dets = _perfect_detections(gt)
    dets[0]["bbox"] = [1, 2, 3]
    with pytest.raises(ValueError, match="bbox must be"):
        evaluate_coco_detections(gt, dets)


def test_nonpositive_maxdets_raises():
    gt = _gt()
    with pytest.raises(ValueError, match="max_dets must be positive"):
        evaluate_coco_detections(gt, _perfect_detections(gt), max_dets=0)


def test_ground_truth_without_area_is_scored_not_crashed():
    """COCOeval raises a bare `KeyError: 'area'`; area is derivable from the bbox."""
    gt = _gt()
    for annotation in gt["annotations"]:
        del annotation["area"]
    result = evaluate_coco_detections(gt, _perfect_detections(gt))
    assert result.ap == pytest.approx(1.0, abs=1e-6)


def test_filling_area_does_not_change_the_score():
    gt_with = _gt()
    gt_without = _gt()
    for annotation in gt_without["annotations"]:
        del annotation["area"]
    detections = _perfect_detections(gt_with)
    scored_with = evaluate_coco_detections(gt_with, detections)
    scored_without = evaluate_coco_detections(gt_without, detections)
    assert scored_without.ap == pytest.approx(scored_with.ap)
    assert scored_without.ap_small == pytest.approx(scored_with.ap_small)
    assert scored_without.ap_medium == pytest.approx(scored_with.ap_medium)


def test_ground_truth_without_iscrowd_is_scored():
    gt = _gt()
    for annotation in gt["annotations"]:
        del annotation["iscrowd"]
    result = evaluate_coco_detections(gt, _perfect_detections(gt))
    assert result.ap == pytest.approx(1.0, abs=1e-6)


def test_annotation_with_neither_area_nor_bbox_is_rejected():
    gt = _gt()
    del gt["annotations"][0]["area"]
    del gt["annotations"][0]["bbox"]
    with pytest.raises(ValueError, match="neither 'area' nor a 4-element 'bbox'"):
        evaluate_coco_detections(gt, [])


def test_filling_does_not_mutate_the_callers_ground_truth():
    gt = _gt()
    for annotation in gt["annotations"]:
        del annotation["area"]
    evaluate_coco_detections(gt, _perfect_detections(gt))
    assert all("area" not in annotation for annotation in gt["annotations"])


def test_missing_gt_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError, match="ground-truth COCO file not found"):
        evaluate_coco_detections("does_not_exist.json", [])


def test_cli_writes_metrics_json(tmp_path, capsys):
    gt = _gt()
    gt_path = tmp_path / "val.coco.json"
    pred_path = tmp_path / "preds.json"
    out_path = tmp_path / "metrics.json"
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    pred_path.write_text(json.dumps(_perfect_detections(gt)), encoding="utf-8")

    rc = main(["--gt", str(gt_path), "--predictions", str(pred_path), "--out", str(out_path)])
    assert rc == 0
    assert out_path.is_file()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["ap"] == pytest.approx(1.0, abs=1e-6)
    assert "AP@[.50:.95]" in capsys.readouterr().out
