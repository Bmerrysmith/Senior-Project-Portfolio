#!/usr/bin/env python3
"""Baseline CONTROL: a stock pretrained segmenter on the RiceSEG task.

WHY THIS EXISTS
---------------
The ImageNet->RiceSEG run of the custom Det-ResNet-50 reached mIoU 0.5816 with
weeds IoU 0.34. Two very different explanations fit that number:

  (a) the task is data-limited  -- RiceSEG simply does not contain enough weed
      pixels to learn the class, so ANY architecture plateaus here; or
  (b) the custom architecture is the limit -- a standard, fully-pretrained
      segmenter would do materially better on the same data.

Those imply opposite next moves (collect/annotate weeds vs. change the model),
so guessing is expensive. This script runs the discriminating experiment that
the v5 optimization report already proposed: "If a pretrained baseline strongly
outperforms WeedDet, the custom architecture is the bottleneck."

WHAT IS HELD FIXED
------------------
Everything except the model. This module imports the split, class weights,
dataset, loss, and confusion-matrix metric directly from riceseg_pretrain rather
than reimplementing them -- a reimplementation would silently make the
comparison invalid. Same seed, same group-aware split, same median-frequency
weights, same CE+Dice loss, same AdamW+cosine schedule, same AMP, same
ConfMat.iou() (mean over PRESENT classes, absent classes reported).

WHAT THIS IS NOT
----------------
This produces a CONTROL measurement, not a deliverable. It deliberately does not
export a WeedDet-compatible backbone: these models have different state-dict
keys and must never be loaded by load_riceseg_backbone(). See --help.

MEASUREMENT NOISE
-----------------
The pretraining run's weeds IoU swung between 0.11 and 0.34 on consecutive
epochs while loss fell smoothly, i.e. best-epoch weeds IoU is partly luck. So
this script reports, per class, the mean and standard deviation over the last
--stability-window epochs alongside the best-epoch value. Compare the STABLE
numbers, not the peaks.

CLI
    python -m agrinav.training.baseline_seg_control \
        --data-root <RiceSEG_root> --arch deeplabv3_resnet50 \
        --epochs 30 --batch-size 8 --img-size 512 \
        --out <out_dir>/baseline_deeplabv3.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from agrinav.training.riceseg_pretrain import (
    CLASS_NAMES,
    NUM_CLASSES,
    ConfMat,
    RiceSegDataset,
    SegLoss,
    _env_versions,
    _git_commit,
    compute_class_weights,
    scan_riceseg,
    split_pairs,
    stability_stats,
)

ARCHS = ("deeplabv3_resnet50", "segformer_b2")


# ================================================================ models
class _DeepLabWrapper(nn.Module):
    """torchvision DeepLabV3 returns an OrderedDict; normalise to a tensor."""

    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, x):
        return self.net(x)["out"]


class _SegformerWrapper(nn.Module):
    """SegFormer emits logits at H/4; upsample to input resolution so the
    ConfMat metric compares like for like with the DeepLab/WeedDet path."""

    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, x):
        logits = self.net(pixel_values=x).logits
        return F.interpolate(logits, size=x.shape[-2:], mode="bilinear", align_corners=False)


def build_model(arch, num_classes=NUM_CLASSES, hf_revision=None, pretrained=True):
    """Return (model, provenance dict).

    Fails closed: if pretrained weights cannot be obtained, this raises rather
    than silently returning a randomly initialised network, which would turn a
    labelled "pretrained baseline" into an unlabelled scratch run. That failure
    mode already bit this project once (riceseg_pretrain's ImageNet guard).
    """
    if arch == "deeplabv3_resnet50":
        from torchvision.models.segmentation import DeepLabV3_ResNet50_Weights, deeplabv3_resnet50

        weights = DeepLabV3_ResNet50_Weights.COCO_WITH_VOC_LABELS_V1 if pretrained else None
        try:
            net = deeplabv3_resnet50(weights=weights, aux_loss=True)
        except Exception as exc:  # network/checkpoint failure
            raise SystemExit(f"[fail-closed] could not load DeepLabV3 weights: {exc}")
        if pretrained and weights is None:
            raise SystemExit("[fail-closed] pretrained requested but no weights resolved")
        # Re-head for the 6 RiceSEG classes (COCO/VOC head is 21-way).
        net.classifier[-1] = nn.Conv2d(256, num_classes, kernel_size=1)
        if net.aux_classifier is not None:
            net.aux_classifier[-1] = nn.Conv2d(256, num_classes, kernel_size=1)
        prov = {
            "arch": arch,
            "model_id": "torchvision/deeplabv3_resnet50",
            "revision": (weights.name if weights is not None else None),
            "pretrained_on": "ImageNet backbone + COCO(VOC labels) segmentation head",
            "head_reinitialised": True,
        }
        return _DeepLabWrapper(net), prov

    if arch == "segformer_b2":
        try:
            from transformers import SegformerForSemanticSegmentation
        except ImportError as exc:
            raise SystemExit(f"[fail-closed] transformers not installed: {exc}")
        model_id = "nvidia/segformer-b2-finetuned-ade-512-512"
        if not pretrained:
            raise SystemExit("--no-pretrained is only implemented for deeplabv3_resnet50")
        try:
            net = SegformerForSemanticSegmentation.from_pretrained(
                model_id, revision=hf_revision, num_labels=num_classes, ignore_mismatched_sizes=True
            )
        except Exception as exc:
            raise SystemExit(f"[fail-closed] could not load {model_id}: {exc}")
        prov = {
            "arch": arch,
            "model_id": model_id,
            "revision": hf_revision,  # None = HEAD; pin for a citable result
            "pretrained_on": "ImageNet-1k backbone + ADE20K semantic segmentation",
            "head_reinitialised": True,
        }
        return _SegformerWrapper(net), prov

    raise SystemExit(f"unknown --arch {arch!r}; choose from {ARCHS}")


# ``stability_stats`` now lives in ``riceseg_pretrain`` (single source of truth,
# re-imported above) so the pretraining run and this control report stability
# identically. It stays importable from this module for backward compatibility.


# ================================================================ main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--arch", default="deeplabv3_resnet50", choices=ARCHS)
    ap.add_argument(
        "--out", required=True, help="path for the run manifest JSON (no backbone is exported)"
    )
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="DeepLabV3/SegFormer are heavier than WeedDet; 8 fits a T4 at 512px",
    )
    ap.add_argument("--img-size", type=int, default=512)
    ap.add_argument(
        "--lr",
        type=float,
        default=3e-4,
        help="default matches the pretraining run for comparability",
    )
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--holdout-country", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--hf-revision", default=None, help="pin the HuggingFace revision for a citable result"
    )
    ap.add_argument(
        "--no-pretrained",
        action="store_true",
        help="scratch control (deeplabv3 only) — isolates the value of pretraining",
    )
    ap.add_argument("--stability-window", type=int, default=5)
    ap.add_argument("--num-workers", type=int, default=2)
    args = ap.parse_args(argv)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[setup] device={device} arch={args.arch}")

    # --- identical data path to riceseg_pretrain (imported, not reimplemented)
    pairs = scan_riceseg(args.data_root)
    countries = sorted({p["country"] for p in pairs})
    print(f"[data] {len(pairs)} tiles | countries: {countries}")
    train_p, val_p = split_pairs(pairs, args.val_ratio, args.seed, args.holdout_country)
    print(
        f"[split] train {len(train_p)} / val {len(val_p)} "
        f"(group-aware by source photo; 0 source overlap)"
    )
    assert not (
        {p["source"] for p in train_p} & {p["source"] for p in val_p}
    ), "source-photo leak between train and val"

    weights = compute_class_weights(train_p).to(device)

    # persistent_workers keeps the worker pool alive across epochs instead of
    # respawning it at every boundary. On Windows each respawn is a full
    # process spawn that re-imports this module, so a mid-run change to any
    # imported source file turns into a crash at the next epoch rather than
    # being ignored. (A sync conflict silently reverting
    # riceseg_pretrain.py first surfaced here -- three epochs in.) Spawning
    # once shrinks that window to startup.
    common = dict(num_workers=args.num_workers)
    if args.num_workers > 0:
        common["persistent_workers"] = True
    tl = DataLoader(
        RiceSegDataset(train_p, args.img_size, augment=True),
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=True,
        drop_last=len(train_p) > args.batch_size,
        **common,
    )
    vl = DataLoader(
        RiceSegDataset(val_p, args.img_size), batch_size=args.batch_size, shuffle=False, **common
    )

    model, prov = build_model(
        args.arch, NUM_CLASSES, args.hf_revision, pretrained=not args.no_pretrained
    )
    model = model.to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(
        f'[model] {prov["model_id"]} rev={prov["revision"]} '
        f"params={n_params/1e6:.1f}M pretrained={not args.no_pretrained}"
    )
    print(f'[model] pretrained_on: {prov["pretrained_on"]}')

    # --- identical optimisation recipe
    crit = SegLoss(weights)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=args.epochs, eta_min=args.lr * 0.01
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    best, best_epoch, best_iou_vec, best_absent = -1.0, 0, None, []
    history = []
    for ep in range(1, args.epochs + 1):
        model.train()
        tot = n = 0
        for x, y in tl:
            x, y = x.to(device), y.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss = crit(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            tot += loss.item()
            n += 1
        sched.step()

        model.eval()
        cm = ConfMat()
        with torch.no_grad():
            for x, y in vl:
                pred = model(x.to(device)).argmax(1).cpu().numpy()
                cm.update(pred, y.numpy())
        iou, miou, absent = cm.iou()
        avg_loss = tot / max(n, 1)
        history.append(
            {
                "epoch": ep,
                "loss": avg_loss,
                "miou": miou,
                "per_class_iou": {
                    nm: (None if np.isnan(v) else float(v)) for nm, v in zip(CLASS_NAMES, iou)
                },
                "absent_classes": absent,
            }
        )
        line = f"epoch {ep:02d}/{args.epochs}  loss={avg_loss:.4f}  mIoU={miou:.4f}  " + " ".join(
            f"{nm}={v:.2f}" for nm, v in zip(CLASS_NAMES, iou)
        )
        if absent:
            line += f'  [absent: {",".join(absent)}]'
        if miou > best:
            best, best_epoch, best_iou_vec, best_absent = miou, ep, iou, absent
            line += "  * best"
        print(line, flush=True)

    stab = stability_stats(history, args.stability_window)

    manifest = {
        "schema_version": "agrinav.baseline_seg_control.run.v1",
        "role": "CONTROL — measures whether the custom Det-ResNet-50 architecture "
        "is the bottleneck. NOT a WeedDet backbone; do not load with "
        "load_riceseg_backbone().",
        "seed": args.seed,
        "git_commit": _git_commit(Path(__file__).resolve().parent),
        "environment": _env_versions(),
        "device": str(device),
        "model": dict(prov, params=int(n_params)),
        "config": vars(args),
        "data": {
            "tiles": len(pairs),
            "train_tiles": len(train_p),
            "val_tiles": len(val_p),
            "countries": countries,
            "holdout_country": args.holdout_country,
        },
        "best": {
            "epoch": best_epoch,
            "miou_present_classes": best,
            "per_class_iou": {
                nm: (None if np.isnan(v) else float(v)) for nm, v in zip(CLASS_NAMES, best_iou_vec)
            },
            "absent_classes": best_absent,
        },
        "stability": stab,
        "history": history,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\n[manifest] {out}")
    print(f"Best mIoU {best:.4f} at epoch {best_epoch}")
    if stab.get("miou_mean") is not None:
        print(
            f'Stable mIoU over last {stab["window"]} epochs: '
            f'{stab["miou_mean"]:.4f} +/- {stab["miou_std"]:.4f}'
        )
        w = stab["per_class"].get("weeds", {})
        if w.get("mean") is not None:
            print(
                f'Stable weeds IoU: {w["mean"]:.4f} +/- {w["std"]:.4f} '
                f'(min {w["min"]:.4f}, max {w["max"]:.4f})'
            )
    print("\nThis is a CONTROL measurement. No backbone was exported by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
