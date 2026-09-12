#!/usr/bin/env python3
"""Convert RiceSEG human semantic masks into COCO instance polygons.

This is NOT auto-annotation: RiceSEG ships expert semantic masks, so extracting
instance polygons from them is a geometry transform of existing ground truth.
The output is therefore valid training-truth for the AgriNav perception task,
mapped onto the project ontology (data/ontology.v1.json):

    RiceSEG semantic value        -> canonical label
    1 green_rice / 2 senescent /  -> rice_protect        (id 1)
    3 rice_panicle
    4 weed                        -> weed_target         (id 2)
    5 duckweed                    -> non_target_aquatic  (id 4)
    0 background                  -> (ignored)

Each connected component of a canonical class becomes one instance polygon. The
archive is read directly; nothing is extracted. Provenance (country, site,
source-photo group, sha256) is carried on every image so a later grouped split
never leaks tiles from one source photo across train/val/test.

Documented simplification: external contours only (interior holes are not
encoded as RLE). Components below --min-area px are dropped as annotation noise,
matching the annotation guide's 16px floor.

CLI:
    python -m agrinav.data.riceseg_masks_to_coco \
        --riceseg-zip RiceSEG.zip \
        --out-json artifacts/detector_v1/riceseg_instances.coco.json
Options: --min-area 16  --simplify-eps 0.004  --max-tiles N  --weed-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

import cv2
import numpy as np
from PIL import Image

# semantic mask value -> canonical ontology label id
RICESEG_TO_CANONICAL = {1: 1, 2: 1, 3: 1, 4: 2, 5: 4}
CANONICAL_CATEGORIES = [
    {"id": 1, "name": "rice_protect", "source_semantic": [1, 2, 3]},
    {"id": 2, "name": "weed_target", "source_semantic": [4]},
    {"id": 4, "name": "non_target_aquatic", "source_semantic": [5]},
]
WEED_CANONICAL_ID = 2
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def member_country_site(member: str):
    """Country/site from a RiceSEG zip member path, anchored on the rgb/label
    directory (mirrors training.riceseg_pretrain.parse_country_site)."""
    parts = PurePosixPath(member).parts
    ki = next((i for i, p in enumerate(parts) if p.lower() in {"rgb", "label"}), None)
    if ki is None or ki < 2:
        return "unknown", None
    if ki == 2:
        return parts[1], None
    return parts[ki - 2], parts[ki - 1]


def source_photo_id(stem: str) -> str:
    return stem.split("_subset", 1)[0]


def mask_to_instances(mask: np.ndarray, min_area: int = 16, simplify_eps: float = 0.004):
    """Return a list of instance dicts for one semantic mask.

    Each dict: {category_id, segmentation:[[x,y,...]], bbox:[x,y,w,h], area}.
    Connected components of each canonical class become separate instances.
    """
    instances = []
    for cat in CANONICAL_CATEGORIES:
        binary = np.isin(mask, cat["source_semantic"]).astype(np.uint8)
        if not binary.any():
            continue
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            eps = simplify_eps * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, eps, True)
            if len(approx) < 3:
                continue
            poly = approx.reshape(-1).astype(float).tolist()
            x, y, w, h = cv2.boundingRect(approx)
            instances.append(
                {
                    "category_id": cat["id"],
                    "segmentation": [poly],
                    "bbox": [float(x), float(y), float(w), float(h)],
                    "area": float(area),
                }
            )
    return instances


def _iter_pairs(archive: zipfile.ZipFile):
    members = {n for n in archive.namelist() if not n.endswith("/")}
    for rgb in sorted(members):
        p = PurePosixPath(rgb)
        if "/rgb/" not in rgb.lower() or p.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        lab_dir = str(p.parent).rsplit("/rgb", 1)[0] + "/label"
        cand = [f"{lab_dir}/{p.name}", f"{lab_dir}/{p.stem}.png"]
        lab = next((c for c in cand if c in members), None)
        if lab:
            yield rgb, lab


def build_coco(zip_path, min_area=16, simplify_eps=0.004, max_tiles=0, weed_only=False):
    zip_path = Path(zip_path)
    images, annotations = [], []
    img_id = ann_id = 0
    skipped_no_target = 0
    with zipfile.ZipFile(zip_path, "r") as archive:
        for rgb, lab in _iter_pairs(archive):
            mask = np.array(Image.open(BytesIO(archive.read(lab))))
            if mask.ndim != 2:
                mask = np.array(Image.open(BytesIO(archive.read(lab))).convert("L"))
            weed_area = int((mask == 4).sum())
            if weed_only and weed_area == 0:
                continue
            instances = mask_to_instances(mask, min_area, simplify_eps)
            if not instances:
                skipped_no_target += 1
                continue
            rgb_bytes = archive.read(rgb)
            country, site = member_country_site(rgb)
            stem = PurePosixPath(rgb).stem
            grp = (
                f"{country}/{site}/{source_photo_id(stem)}"
                if site
                else f"{country}/{source_photo_id(stem)}"
            )
            h, w = mask.shape[:2]
            img_id += 1
            images.append(
                {
                    "id": img_id,
                    "file_name": rgb,
                    "width": int(w),
                    "height": int(h),
                    "sha256": hashlib.sha256(rgb_bytes).hexdigest(),
                    "source_dataset": "riceseg",
                    "country": country,
                    "site": site,
                    "source_photo_id": source_photo_id(stem),
                    "group_id": f"riceseg:{grp}",
                    "view": None,
                    "weed_pixel_area": weed_area,
                    "annotation_origin": "riceseg_human_semantic_mask",
                    "review_status": "derived_from_human_mask",
                }
            )
            for inst in instances:
                ann_id += 1
                annotations.append({"id": ann_id, "image_id": img_id, "iscrowd": 0, **inst})
            if max_tiles and img_id >= max_tiles:
                break

    weed_imgs = sum(1 for im in images if im["weed_pixel_area"] > 0)
    weed_anns = sum(1 for a in annotations if a["category_id"] == WEED_CANONICAL_ID)
    coco = {
        "info": {
            "description": "RiceSEG human semantic masks converted to instance polygons",
            "ontology": "data/ontology.v1.json",
            "annotation_origin": "riceseg_human_semantic_mask",
            "notes": "External contours only; interior holes not RLE-encoded. "
            "Valid training truth (human masks), not model proposals.",
            "params": {"min_area": min_area, "simplify_eps": simplify_eps, "weed_only": weed_only},
        },
        "categories": [{"id": c["id"], "name": c["name"]} for c in CANONICAL_CATEGORIES],
        "images": images,
        "annotations": annotations,
    }
    summary = {
        "images": len(images),
        "annotations": len(annotations),
        "weed_positive_images": weed_imgs,
        "weed_target_instances": weed_anns,
        "images_skipped_no_target": skipped_no_target,
        "source_groups": len({im["group_id"] for im in images}),
        "countries": sorted({im["country"] for im in images}),
    }
    return coco, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--riceseg-zip", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--min-area", type=int, default=16)
    ap.add_argument("--simplify-eps", type=float, default=0.004)
    ap.add_argument("--max-tiles", type=int, default=0)
    ap.add_argument("--weed-only", action="store_true")
    args = ap.parse_args(argv)

    coco, summary = build_coco(
        args.riceseg_zip, args.min_area, args.simplify_eps, args.max_tiles, args.weed_only
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(coco), encoding="utf-8")
    print(f"Wrote {args.out_json}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
