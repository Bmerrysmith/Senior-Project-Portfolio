#!/usr/bin/env python3
"""Convert the Paddy Rice Imagery (DatasetNinja/Supervisely) panicle polygons
into COCO instance polygons, mapped to the AgriNav ontology.

The dataset ships human panicle polygons for aerial (UAV) rice imagery. Panicle
is part of cultivated rice, so it maps to `rice_protect` (data/ontology.v1.json).

IMPORTANT LIMITATION: these masks cover ONLY panicles, not whole rice plants, so
this is *partial* rice coverage and aerial-only. It is emitted as a SEPARATE
COCO file (source_dataset="paddy_panicle", per-image note) so it is never naively
merged with RiceSEG full-plant rice masks — a later training config decides
whether to include it as auxiliary aerial context. It contains NO weeds.

Reads annotations directly from the .tar; image pixels are not extracted. Frames
are grouped by capture session (the name before "_Frame_") so adjacent frames
never leak across splits.

CLI:
    python -m agrinav.data.paddy_supervisely_to_coco \
        --tar paddy-rice-imagery-DatasetNinja.tar \
        --out-json artifacts/detector_v1/paddy_panicle.coco.json
Options: --hash-images (compute image sha256; slower) --max-frames N
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

RICE_PROTECT_ID = 1
SESSION_RE = re.compile(r"^(?P<session>.+?)_Frame_\d+", re.IGNORECASE)


def session_of(stem: str) -> str:
    m = SESSION_RE.match(stem)
    return m.group("session") if m else stem


def polygon_area(pts):
    """Shoelace area of a list of [x, y] exterior points."""
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def supervisely_objects_to_annotations(ann, class_title="panicle", min_area=16):
    """Return COCO annotation fragments (no id/image_id) for one Supervisely ann."""
    out = []
    for obj in ann.get("objects", []):
        if obj.get("geometryType") != "polygon":
            continue
        if obj.get("classTitle") != class_title:
            continue
        exterior = obj.get("points", {}).get("exterior", [])
        if len(exterior) < 3:
            continue
        area = polygon_area(exterior)
        if area < min_area:
            continue
        xs = [p[0] for p in exterior]
        ys = [p[1] for p in exterior]
        flat = [float(c) for p in exterior for c in p]
        out.append(
            {
                "category_id": RICE_PROTECT_ID,
                "segmentation": [flat],
                "bbox": [
                    float(min(xs)),
                    float(min(ys)),
                    float(max(xs) - min(xs)),
                    float(max(ys) - min(ys)),
                ],
                "area": float(area),
                "iscrowd": 0,
            }
        )
    return out


def build_coco(tar_path, hash_images=False, max_frames=0, min_area=16):
    tar_path = Path(tar_path)
    images, annotations = [], []
    img_id = ann_id = 0
    with tarfile.open(tar_path, "r") as tar:
        ann_members = sorted(n for n in tar.getnames() if "/ann/" in n and n.endswith(".json"))
        for member in ann_members:
            ann = json.load(tar.extractfile(member))
            frags = supervisely_objects_to_annotations(ann, min_area=min_area)
            if not frags:
                continue
            p = PurePosixPath(member)
            original_split = p.parts[0]
            img_name = p.name[: -len(".json")]  # strip .json -> x.png
            stem = PurePosixPath(img_name).stem
            img_member = f"{original_split}/img/{img_name}"
            sha = None
            if hash_images:
                try:
                    sha = hashlib.sha256(tar.extractfile(img_member).read()).hexdigest()
                except Exception:
                    sha = None
            size = ann.get("size", {})
            img_id += 1
            images.append(
                {
                    "id": img_id,
                    "file_name": img_member,
                    "width": int(size.get("width", 0)),
                    "height": int(size.get("height", 0)),
                    "sha256": sha,
                    "source_dataset": "paddy_panicle",
                    "group_id": f"paddy:{session_of(stem)}",
                    "session": session_of(stem),
                    "view": "aerial",
                    "original_split": original_split,
                    "annotation_origin": "paddy_supervisely_human_polygon",
                    "annotation_note": "panicle_only_partial_rice_coverage; no weeds",
                    "review_status": "derived_from_human_polygon",
                }
            )
            for frag in frags:
                ann_id += 1
                annotations.append({"id": ann_id, "image_id": img_id, **frag})
            if max_frames and img_id >= max_frames:
                break

    coco = {
        "info": {
            "description": "Paddy Rice Imagery panicle polygons -> rice_protect",
            "ontology": "data/ontology.v1.json",
            "annotation_origin": "paddy_supervisely_human_polygon",
            "limitation": "panicle-only partial rice coverage; aerial; no weeds. "
            "Auxiliary aerial context, not a substitute for full-plant rice masks.",
        },
        "categories": [{"id": RICE_PROTECT_ID, "name": "rice_protect"}],
        "images": images,
        "annotations": annotations,
    }
    summary = {
        "images": len(images),
        "annotations": len(annotations),
        "sessions": len({im["session"] for im in images}),
        "hashed_images": sum(1 for im in images if im["sha256"]),
    }
    return coco, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tar", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--hash-images", action="store_true")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--min-area", type=int, default=16)
    args = ap.parse_args(argv)

    coco, summary = build_coco(args.tar, args.hash_images, args.max_frames, args.min_area)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(coco), encoding="utf-8")
    print(f"Wrote {args.out_json}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
