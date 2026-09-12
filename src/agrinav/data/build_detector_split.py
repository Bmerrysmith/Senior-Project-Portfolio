#!/usr/bin/env python3
"""Build a source-grouped train/val/test split for the AgriNav detector data.

Enforces the deployment roadmap Gate 2 split policy:
  * assignment is at the highest leakage-risk unit (image `group_id`: the RiceSEG
    source photo, or the paddy capture session) -- NEVER at the tile/frame level;
  * no group crosses splits, so overlapping tiles and adjacent video frames stay
    together (the exact failure the audit found in the old COCO split);
  * groups are stratified by (source_dataset, country, has_weed) so every split
    keeps weed instances and country coverage;
  * the test split is marked sealed in the manifest.

Consumes one or more COCO files produced by riceseg_masks_to_coco.py /
paddy_supervisely_to_coco.py (images carry `group_id`, `source_dataset`,
`country`, and weed info). Emits a split manifest plus per-split COCO files, and
asserts zero group overlap before writing.

CLI:
    python -m agrinav.data.build_detector_split \
        --coco artifacts/detector_v1/riceseg_instances.coco.json \
        --out-dir artifacts/detector_v1/split_v1
Options: --ratios 0.7 0.15 0.15  --seed 20260720  --include-paddy (adds paddy COCO)
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

WEED_CATEGORY_ID = 2


def stratified_group_split(groups, ratios=(0.7, 0.15, 0.15), seed=20260720):
    """groups: list of {group_id, stratum}. Returns {group_id: split} with each
    whole group in exactly one split, stratified proportionally per stratum."""
    assert abs(sum(ratios) - 1.0) < 1e-6, "ratios must sum to 1"
    rng = random.Random(seed)
    by_stratum = defaultdict(list)
    for g in groups:
        by_stratum[g["stratum"]].append(g["group_id"])
    assignment = {}
    for stratum in sorted(by_stratum):
        gids = sorted(set(by_stratum[stratum]))
        rng.shuffle(gids)
        n = len(gids)
        n_tr = round(n * ratios[0])
        n_va = round(n * ratios[1])
        for i, gid in enumerate(gids):
            assignment[gid] = "train" if i < n_tr else "val" if i < n_tr + n_va else "test"
    return assignment


def _group_meta(coco):
    """Per-group stratum metadata from a COCO doc."""
    weed_img_ids = {
        a["image_id"] for a in coco["annotations"] if a["category_id"] == WEED_CATEGORY_ID
    }
    groups = {}
    for im in coco["images"]:
        gid = im["group_id"]
        g = groups.setdefault(
            gid,
            {
                "group_id": gid,
                "source_dataset": im.get("source_dataset", "unknown"),
                "country": im.get("country") or "na",
                "has_weed": False,
                "n_images": 0,
            },
        )
        g["n_images"] += 1
        if im["id"] in weed_img_ids:
            g["has_weed"] = True
    for g in groups.values():
        g["stratum"] = f"{g['source_dataset']}|{g['country']}|weed={int(g['has_weed'])}"
    return groups


def _filter_coco(coco, image_ids):
    keep = set(image_ids)
    imgs = [im for im in coco["images"] if im["id"] in keep]
    anns = [a for a in coco["annotations"] if a["image_id"] in keep]
    return {
        "info": coco.get("info", {}),
        "categories": coco["categories"],
        "images": imgs,
        "annotations": anns,
    }


def build_split(cocos, ratios, seed):
    """cocos: list of loaded COCO docs (image ids must be unique per doc; we
    namespace by doc index). Returns (assignment, merged, per_split_stats)."""
    merged = {
        "info": {"description": "AgriNav detector split source"},
        "categories": cocos[0]["categories"],
        "images": [],
        "annotations": [],
    }
    img_offset = ann_offset = 0
    for doc in cocos:
        id_map = {}
        for im in doc["images"]:
            new = im["id"] + img_offset
            id_map[im["id"]] = new
            merged["images"].append({**im, "id": new})
        for a in doc["annotations"]:
            merged["annotations"].append(
                {**a, "id": a["id"] + ann_offset, "image_id": id_map[a["image_id"]]}
            )
        img_offset = max((im["id"] for im in merged["images"]), default=0) + 1
        ann_offset = max((a["id"] for a in merged["annotations"]), default=0) + 1

    groups = _group_meta(merged)
    assignment = stratified_group_split(list(groups.values()), ratios, seed)

    # Assign each image to its group's split and assert no group crosses splits.
    group_to_split = defaultdict(set)
    split_images = defaultdict(list)
    for im in merged["images"]:
        sp = assignment[im["group_id"]]
        group_to_split[im["group_id"]].add(sp)
        split_images[sp].append(im["id"])
    crossing = {g: s for g, s in group_to_split.items() if len(s) > 1}
    assert not crossing, f"groups cross splits: {list(crossing)[:5]}"

    weed_img_ids = {
        a["image_id"] for a in merged["annotations"] if a["category_id"] == WEED_CATEGORY_ID
    }
    stats = {}
    for sp in ("train", "val", "test"):
        ids = split_images[sp]
        stats[sp] = {
            "images": len(ids),
            "groups": len(
                {
                    merged_im["group_id"]
                    for merged_im in merged["images"]
                    if merged_im["id"] in set(ids)
                }
            ),
            "weed_positive_images": sum(1 for i in ids if i in weed_img_ids),
            "annotations": sum(1 for a in merged["annotations"] if a["image_id"] in set(ids)),
        }
    return assignment, merged, split_images, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--coco",
        action="append",
        required=True,
        type=Path,
        help="COCO file(s) to include; repeatable",
    )
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--ratios", nargs=3, type=float, default=[0.7, 0.15, 0.15])
    ap.add_argument("--seed", type=int, default=20260720)
    args = ap.parse_args(argv)

    cocos = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.coco]
    assignment, merged, split_images, stats = build_split(cocos, tuple(args.ratios), args.seed)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for sp in ("train", "val", "test"):
        doc = _filter_coco(merged, split_images[sp])
        (args.out_dir / f"{sp}.coco.json").write_text(json.dumps(doc), encoding="utf-8")

    manifest = {
        "schema_version": "agrinav.detector_split.v1",
        "seed": args.seed,
        "ratios": {"train": args.ratios[0], "val": args.ratios[1], "test": args.ratios[2]},
        "policy": "group-level (source photo / capture session); zero group overlap; "
        "stratified by source_dataset|country|has_weed",
        "test_sealed": True,
        "sources": [str(p) for p in args.coco],
        "stats": stats,
        "group_assignment": assignment,
    }
    (args.out_dir / "split-v1.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote split to {args.out_dir}")
    for sp in ("train", "val", "test"):
        s = stats[sp]
        print(
            f"  {sp:5s}: {s['images']:5d} imgs | {s['groups']:4d} groups | "
            f"{s['weed_positive_images']:4d} weed-img | {s['annotations']:6d} anns"
        )
    print(f"  groups total: {len(assignment)} | zero group overlap asserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
