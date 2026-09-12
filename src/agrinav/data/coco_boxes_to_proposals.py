#!/usr/bin/env python3
"""Convert the rice_detection COCO boxes into an UNREVIEWED proposal layer.

The COCO detector export has human *boxes* (rice + weed) but (a) no masks,
(b) a capture-series-contaminated split, and (c) very few weeds. Under the
project ontology and annotation guide, these cannot enter the training split as
truth. This tool emits them as PROPOSALS only:

  * boxes are remapped to ontology categories (rice -> rice_protect,
    weed -> weed_target) and kept as seed geometry for a box->mask refinement
    step (SAM2.1 per configs/annotation/pilot_v1.json);
  * every annotation is tagged review_status="unreviewed_proposal";
  * every image is tagged split_status="original_split_contaminated_rebuild_required"
    and grouped by capture family so a future grouped split can be built after
    provenance recovery;
  * NOTHING here is training truth until a human reviews it in CVAT.

This keeps COCO in the "human masks + model proposals" workflow the user chose:
RiceSEG/paddy are human-mask truth; COCO is a proposal pending SAM + review.

CLI:
    python -m agrinav.data.coco_boxes_to_proposals \
        --coco-zip rice_detection_for_export.v1i.coco.zip \
        --out-json artifacts/detector_v1/coco_proposals_unreviewed.coco.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

from agrinav.data.build_annotation_pilot import detector_capture_family

# rice_detection category id -> ontology canonical id
COCO_TO_CANONICAL = {1: 1, 2: 2}  # 1 rice->rice_protect, 2 weed->weed_target
CANONICAL_NAME = {1: "rice_protect", 2: "weed_target"}


def _find_coco_json(members):
    cands = [
        m
        for m in members
        if m.endswith("_annotations.coco.json") or m.endswith("annotations.coco.json")
    ]
    if not cands:
        cands = [m for m in members if m.endswith(".json")]
    if not cands:
        raise SystemExit("no COCO annotation json found in archive")
    return sorted(cands, key=len)[0]


def build_proposals(zip_path):
    zip_path = Path(zip_path)
    images, annotations = [], []
    with zipfile.ZipFile(zip_path, "r") as z:
        members = [m for m in z.namelist() if not m.endswith("/")]
        # Merge every split's json (train/valid/test) — we discard the
        # contaminated split boundary and rebuild groups from capture family.
        json_members = [m for m in members if m.endswith(".coco.json")]
        src_cats = {}
        img_id = ann_id = 0
        seen_files = {}
        for jm in sorted(json_members):
            doc = json.loads(z.read(jm))
            for c in doc.get("categories", []):
                src_cats[c["id"]] = c["name"]
            split_dir = PurePosixPath(jm).parent
            local_to_global = {}
            for im in doc["images"]:
                fname = im["file_name"]
                member = f"{split_dir}/{fname}" if str(split_dir) != "." else fname
                if member not in seen_files:
                    try:
                        raw = z.read(member)
                        sha = hashlib.sha256(raw).hexdigest()
                    except KeyError:
                        sha = None
                    family, conf = detector_capture_family(fname)
                    img_id += 1
                    seen_files[member] = img_id
                    images.append(
                        {
                            "id": img_id,
                            "file_name": member,
                            "width": im.get("width"),
                            "height": im.get("height"),
                            "sha256": sha,
                            "source_dataset": "rice_detection_coco",
                            "group_id": f"rice_detection:{family}",
                            "capture_family": family,
                            "group_confidence": conf,
                            "view": None,
                            "original_split": str(split_dir),
                            "split_status": "original_split_contaminated_rebuild_required",
                            "annotation_origin": "coco_human_box_pending_sam_mask",
                            "review_status": "unreviewed_proposal",
                        }
                    )
                local_to_global[im["id"]] = seen_files[member]
            for a in doc["annotations"]:
                cat = COCO_TO_CANONICAL.get(a["category_id"])
                if cat is None:
                    continue
                ann_id += 1
                annotations.append(
                    {
                        "id": ann_id,
                        "image_id": local_to_global[a["image_id"]],
                        "category_id": cat,
                        "bbox": [float(v) for v in a["bbox"]],
                        "segmentation": [],  # to be filled by SAM box->mask
                        "area": float(a.get("area", a["bbox"][2] * a["bbox"][3])),
                        "iscrowd": 0,
                        "annotation_origin": "coco_human_box",
                        "review_status": "unreviewed_proposal",
                    }
                )
    coco = {
        "info": {
            "description": "rice_detection COCO boxes as UNREVIEWED proposals",
            "ontology": "data/ontology.v1.json",
            "WARNING": "NOT training truth. Boxes only, no masks. Original split "
            "is capture-series contaminated. Refine box->mask with SAM "
            "(configs/annotation/pilot_v1.json), human-review in CVAT, "
            "then rebuild a grouped split before any training use.",
            "source_categories": src_cats,
        },
        "categories": [{"id": i, "name": n} for i, n in CANONICAL_NAME.items()],
        "images": images,
        "annotations": annotations,
    }
    weed = sum(1 for a in annotations if a["category_id"] == 2)
    summary = {
        "images": len(images),
        "annotations": len(annotations),
        "weed_proposals": weed,
        "rice_proposals": len(annotations) - weed,
        "capture_families": len({im["capture_family"] for im in images}),
    }
    return coco, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coco-zip", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    args = ap.parse_args(argv)
    coco, summary = build_proposals(args.coco_zip)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(coco), encoding="utf-8")
    print(f"Wrote {args.out_json} (UNREVIEWED proposals — not training truth)")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
