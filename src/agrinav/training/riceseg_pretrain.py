"""
riceseg_pretrain.py — pretrain WeedDet's Det-ResNet-50 on RiceSEG segmentation.

Why: ImageNet can only fill ~92% of Det-ResNet-50 (custom stem + layer1.0 stay
random), and freezing ImageNet BN behind that random stem regressed detection
(v6b AP@50 0.017 vs scratch 0.166). Training the WHOLE backbone on in-domain
rice imagery (RiceSEG, arXiv:2504.02880 — has an explicit `weeds` class) makes
every backbone tensor + BN stat coherent, including the stem.

Exports a checkpoint whose keys are byte-for-byte `WeedDet.backbone.*`
(same DetResNet50 class -> same keys), optionally `fpn.*` too.

Historical integration API (research only; read the July 20 audit before reuse):
    from agrinav.training.riceseg_pretrain import load_riceseg_backbone, freeze_backbone_bn
    load_riceseg_backbone(weeddet_model, 'riceseg_backbone.pth')
    # BN option A (recommended, matches v5GPT): do nothing — all BN trainable
    # BN option B: freeze_backbone_bn(weeddet_model)  (re-apply after EVERY .train())
    # NEVER wd.apply_bn_policy() on a riceseg backbone — that is the F1+F2 regression.

CLI:
    python -m agrinav.training.riceseg_pretrain --self-test                      # no data needed
    python -m agrinav.training.riceseg_pretrain --data-root RiceSEG --overfit 8 --batch-size 4
    python -m agrinav.training.riceseg_pretrain --data-root RiceSEG --epochs 30 --out riceseg_backbone.pth
Options: --img-size 512 --lr 3e-4 --val-ratio 0.1 --holdout-country NAME
         --no-imagenet --include-fpn
"""

import argparse
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


# ---------------------------------------------------------------- import WeedDet
def _import_wd():
    here = Path(__file__).resolve().parent
    for p in (str(here.parent), str(here.parent / "models"), str(here)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for name in ("agrinav.models.weeddet_v6b", "models.weeddet_v6b", "weeddet_v6b"):
        try:
            mod = __import__(name, fromlist=["x"])
            return mod
        except ImportError:
            continue
    raise ImportError("weeddet_v6b.py not importable — put it in models/ or on sys.path")


wd = _import_wd()

NUM_CLASSES = 6  # 0 bg, 1 green veg, 2 senescent, 3 panicle, 4 weeds, 5 duckweed
CLASS_NAMES = ["background", "green_veg", "senescent", "panicle", "weeds", "duckweed"]
IMAGENET_MEAN, IMAGENET_STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


# ================================================================ model
class RiceSegModel(nn.Module):
    """DetResNet50 + eFPN (names match WeedDet -> identical state-dict keys)
    + a light segmentation decoder. Only backbone(+fpn) get exported."""

    def __init__(self, num_classes=NUM_CLASSES, feat=256):
        super().__init__()
        self.backbone = wd.DetResNet50()
        self.fpn = wd.eFPN(512, 1024, 2048, feat)
        self.decoder = nn.Sequential(
            nn.Conv2d(feat, feat, 3, padding=1, bias=False),
            nn.BatchNorm2d(feat),
            nn.ReLU(inplace=True),
            nn.Conv2d(feat, feat, 3, padding=1, bias=False),
            nn.BatchNorm2d(feat),
            nn.ReLU(inplace=True),
        )
        self.classifier = nn.Conv2d(feat, num_classes, 1)

    def forward(self, x):
        c3, c4, c5 = self.backbone(x)
        p3, p4, p5 = self.fpn(c3, c4, c5)  # strides 4/8/16
        f = (
            p3
            + F.interpolate(p4, size=p3.shape[-2:], mode="bilinear", align_corners=False)
            + F.interpolate(p5, size=p3.shape[-2:], mode="bilinear", align_corners=False)
        )
        y = self.classifier(self.decoder(f))
        return F.interpolate(y, size=x.shape[-2:], mode="bilinear", align_corners=False)


# ================================================================ export / load
def export_backbone(model, path, include_fpn=False):
    keep = ("backbone.", "fpn.") if include_fpn else ("backbone.",)
    sd = {k: v.cpu() for k, v in model.state_dict().items() if k.startswith(keep)}
    torch.save(sd, path)
    print(f"[export] {len(sd)} tensors -> {path}")
    return sd


def sha256_file(path, chunk_size=1024 * 1024):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repo_hint):
    try:
        import subprocess

        out = subprocess.check_output(
            ["git", "-C", str(repo_hint), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:
        return None


def _env_versions():
    import platform

    versions = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
    }
    try:
        import torchvision

        versions["torchvision"] = torchvision.__version__
    except Exception:
        pass
    return versions


def write_run_manifest(path, manifest):
    """Emit one immutable JSON run record. The audit found runs were identified
    only by mutable notebook/Drive paths with no code/data/env hashes
    (deployment roadmap Gate 1, "Every run must record")."""
    import json

    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[manifest] {path}")


def save_full_checkpoint(path, model, optimizer, scheduler, epoch, best_miou, config, history):
    """Save a resumable segmentation checkpoint alongside the exported backbone
    (deployment roadmap Gate 4, RiceSEG repair #7). Distinct from the
    backbone-only export consumed by WeedDet."""
    torch.save(
        {
            "schema_version": "agrinav.riceseg_pretrain.fullckpt.v1",
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "epoch": epoch,
            "best_miou": best_miou,
            "config": config,
            "history": history,
            "rng": {
                "python": random.getstate(),
                "numpy": np.random.get_state(),
                "torch": torch.get_rng_state(),
            },
        },
        path,
    )
    print(f"[checkpoint] full resumable state -> {path}")


def load_riceseg_backbone(weeddet_model, ckpt_path, verbose=True, require_fpn=False):
    """Drop-in replacement for wd.load_imagenet_backbone — fills the WHOLE
    backbone (stem + layer1.0 included). Keep all BN trainable afterwards
    (or freeze ALL with freeze_backbone_bn) — never wd.apply_bn_policy.

    Fails closed: the checkpoint must cover EVERY expected backbone tensor
    (optionally fpn.* too) with a matching shape. A partial or shape-mismatched
    load raises instead of silently training from a mostly-random backbone
    (deep audit 2026-07-20, Section 9.4, "partial validation of loaded weights").
    """
    sd = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    sd = sd.get("state_dict", sd)
    model_sd = weeddet_model.state_dict()
    expected = {k for k in model_sd if k.startswith("backbone.")}
    if require_fpn:
        expected |= {k for k in model_sd if k.startswith("fpn.")}
    loadable, shape_mismatch = {}, []
    for k in sorted(expected):
        if k in sd:
            if tuple(sd[k].shape) == tuple(model_sd[k].shape):
                loadable[k] = sd[k]
            else:
                shape_mismatch.append((k, tuple(sd[k].shape), tuple(model_sd[k].shape)))
    missing = sorted(expected - set(loadable) - {k for k, *_ in shape_mismatch})
    if missing or shape_mismatch:
        raise ValueError(
            f"riceseg load is incomplete: {len(loadable)}/{len(expected)} expected "
            f"tensors matched; missing={missing[:6]}"
            f"{'...' if len(missing) > 6 else ''}; "
            f"shape_mismatch={shape_mismatch[:3]}. Do NOT train from this state."
        )
    weeddet_model.load_state_dict(loadable, strict=False)
    unexpected = sorted(set(sd) - set(model_sd))
    if verbose:
        n_backbone = sum(1 for k in loadable if k.startswith("backbone."))
        print(
            f"[riceseg] loaded {len(loadable)}/{len(expected)} expected tensors "
            f"({n_backbone} backbone); {len(unexpected)} checkpoint tensors ignored"
        )
    return len(loadable)


def freeze_backbone_bn(weeddet_model):
    """BN option B: freeze ALL backbone BN with the (now in-domain) RiceSEG
    stats. Re-apply after EVERY model.train() call."""
    n = 0
    for name, m in weeddet_model.named_modules():
        if name.startswith("backbone.") and isinstance(m, nn.BatchNorm2d):
            m.eval()
            for p in m.parameters():
                p.requires_grad = False
            n += 1
    return n


# ================================================================ data
def parse_country_site(rgb_path, root):
    """Country/site for a RiceSEG rgb (or label) path.

    The supplied archive extracts to a single dataset wrapper directory that
    then holds one directory per country, e.g.

        <root>/global rice segmentation/China/GD/rgb/<tile>.jpg     (has site)
        <root>/global rice segmentation/India/rgb/<tile>.jpg        (no site)

    so relative to ``root`` the wrapper is ``parts[0]`` and the country is the
    component immediately after it. The previous implementation used
    ``parts[0]`` as the country and therefore labelled every tile
    "global rice segmentation", breaking country holdout and country reporting
    (deep audit 2026-07-20, Section 9.4). This anchors on the rgb/label kind
    directory instead — mirroring scripts/build_annotation_pilot so both tools
    agree on country/site — and returns ``(country, site_or_None)``.
    """
    parts = Path(rgb_path).relative_to(root).parts
    kind_index = next(
        (i for i, part in enumerate(parts) if part.lower() in {"rgb", "label"}),
        None,
    )
    if kind_index is None or kind_index < 2:
        return "unknown", None
    if kind_index == 2:
        return parts[1], None
    return parts[kind_index - 2], parts[kind_index - 1]


def scan_riceseg(data_root):
    """Find (rgb, label, country, site, source) tuples. Layout: any depth of
    <wrapper>/<country>[/<site>]/rgb/<tile> with a sibling label/ dir holding
    the same-name mask. Country/site come from ``parse_country_site``."""
    root = Path(data_root)
    pairs = []
    for rgb in sorted(root.glob("**/rgb/*")):
        if rgb.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        lab_dir = rgb.parent.parent / "label"
        lab = None
        for cand in (lab_dir / rgb.name, lab_dir / (rgb.stem + ".png")):
            if cand.exists():
                lab = cand
                break
        if lab is None:
            continue
        country, site = parse_country_site(rgb, root)
        m = re.split(r"_subset", rgb.stem, maxsplit=1)
        # Group by country/site/source-photo so overlapping tiles from one
        # photo never cross a split even when two sites reuse a photo stem.
        group_prefix = f"{country}/{site}" if site else country
        source_id = f"{group_prefix}/{m[0]}"
        pairs.append(
            {
                "rgb": str(rgb),
                "label": str(lab),
                "country": country,
                "site": site,
                "source": source_id,
            }
        )
    if not pairs:
        raise FileNotFoundError(f"no rgb/label pairs under {data_root}")
    return pairs


def split_pairs(pairs, val_ratio=0.1, seed=42, holdout_country=None):
    """Group-aware split: all tiles of one source photo stay in one split
    (tiles overlap -> random split would leak). Optional country holdout."""
    if holdout_country:
        train = [p for p in pairs if p["country"].lower() != holdout_country.lower()]
        val = [p for p in pairs if p["country"].lower() == holdout_country.lower()]
        assert val, f"no tiles for country {holdout_country}"
        return train, val
    groups = defaultdict(list)
    for p in pairs:
        groups[p["source"]].append(p)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    target = val_ratio * len(pairs)
    val, n = [], 0
    for k in keys:
        if n >= target:
            break
        val += groups[k]
        n += len(groups[k])
    val_set = {id(p) for p in val}
    train = [p for p in pairs if id(p) not in val_set]
    assert not ({p["source"] for p in train} & {p["source"] for p in val})
    return train, val


def compute_class_weights(pairs, num_classes=NUM_CLASSES, max_samples=400, clamp=(0.5, 8.0)):
    """Median-frequency balancing, clamped. (Effective-number saturates on
    pixel counts in the millions -> degenerate weights; median-freq verified
    sane on RiceSEG: green_veg -> 0.5, weeds/duckweed -> 8.0.)"""
    from PIL import Image

    counts = np.zeros(num_classes, dtype=np.float64)
    step = max(1, len(pairs) // max_samples)
    for p in pairs[::step]:
        m = np.asarray(Image.open(p["label"]))
        for c in range(num_classes):
            counts[c] += (m == c).sum()
    freq = counts / max(counts.sum(), 1)
    med = np.median(freq[freq > 0])
    w = np.where(freq > 0, med / np.maximum(freq, 1e-12), 0.0)
    w = np.clip(w, clamp[0], clamp[1])
    print("[weights]", {n: round(float(x), 2) for n, x in zip(CLASS_NAMES, w)})
    return torch.tensor(w, dtype=torch.float32)


class RiceSegDataset(Dataset):
    def __init__(self, pairs, img_size=512, augment=False, ignore_index=None):
        self.pairs, self.img_size, self.augment = pairs, img_size, augment
        # ignore_index: an out-of-range value (e.g. 255 void) that is permitted
        # and preserved rather than rejected. Default None = strict.
        self.ignore_index = ignore_index

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, i):
        from PIL import Image

        p = self.pairs[i]
        img = Image.open(p["rgb"]).convert("RGB")
        lab = Image.open(p["label"])
        if img.size != (self.img_size, self.img_size):
            img = img.resize((self.img_size,) * 2, Image.BILINEAR)
            lab = lab.resize((self.img_size,) * 2, Image.NEAREST)
        if self.augment and random.random() > 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            lab = lab.transpose(Image.FLIP_LEFT_RIGHT)
        x = torch.from_numpy(np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0)
        x = (x - torch.tensor(IMAGENET_MEAN)[:, None, None]) / torch.tensor(IMAGENET_STD)[
            :, None, None
        ]
        # Validate rather than clip. The old unconditional clip silently mapped
        # any unexpected value (e.g. a 255 void pixel) to duckweed (deep audit
        # 2026-07-20, Section 9.4). Unknown values now fail loudly.
        arr = np.asarray(lab, dtype=np.int64)
        valid = (arr >= 0) & (arr < NUM_CLASSES)
        if self.ignore_index is not None:
            valid |= arr == self.ignore_index
        if not valid.all():
            bad = np.unique(arr[~valid]).tolist()
            allowed = f"[0, {NUM_CLASSES - 1}]"
            if self.ignore_index is not None:
                allowed += f" or ignore_index={self.ignore_index}"
            raise ValueError(f"mask {p['label']} has values outside {allowed}: {bad}")
        y = torch.from_numpy(arr)
        return x, y


# ================================================================ loss / metrics
LOSSES = ("ce_dice", "focal_tversky")


class SegLoss(nn.Module):
    """class-weighted CE + soft Dice.

    ``dice_weighted`` and ``ignore_background`` are OFF by default so this loss
    is numerically identical to the original recipe. The baseline control
    (``baseline_seg_control.py``) imports this class and calls ``SegLoss(weights)``
    with defaults, so the A/B stays comparable — the knobs only change a
    pretraining run that opts in. Weighting the Dice term (or dropping the huge,
    easy background channel from it) gives the region loss the same minority
    emphasis the weighted CE already has, instead of letting background — whose
    Dice is ~1 and gradient ~0 — dilute the per-class mean.
    """

    def __init__(
        self,
        class_weights=None,
        dice_w=0.5,
        dice_weighted=False,
        ignore_background=False,
    ):
        super().__init__()
        self.ce = nn.CrossEntropyLoss(weight=class_weights)
        self.dice_w = dice_w
        self.ignore_background = ignore_background
        if dice_weighted and class_weights is not None:
            self.register_buffer("dice_weights", class_weights / class_weights.sum())
        else:
            self.dice_weights = None

    def forward(self, logits, target):
        ce = self.ce(logits, target)
        prob = logits.softmax(1)
        oh = F.one_hot(target, logits.shape[1]).permute(0, 3, 1, 2).float()
        inter = (prob * oh).sum((0, 2, 3))
        card = prob.sum((0, 2, 3)) + oh.sum((0, 2, 3))
        per_class = 1.0 - (2 * inter + 1.0) / (card + 1.0)  # [C], 0 = perfect
        start = 1 if self.ignore_background else 0
        pc = per_class[start:]
        if self.dice_weights is not None:
            w = self.dice_weights[start:]
            dice = (pc * w).sum() / w.sum().clamp_min(1e-12)
        else:
            dice = pc.mean()
        return ce + self.dice_w * dice


class FocalTverskyLoss(nn.Module):
    """Focal-Tversky loss for minority-class recall (weeds / duckweed).

    ``alpha`` weights false positives, ``beta`` false negatives; ``beta > alpha``
    pushes recall on the rare classes that median-frequency CE alone struggles
    with, and ``gamma > 1`` focuses gradient on the hard classes. Background is
    excluded by default so it cannot dominate the class mean. A CE term is kept
    for optimisation stability.
    """

    def __init__(
        self,
        class_weights=None,
        alpha=0.3,
        beta=0.7,
        gamma=1.3333,
        ignore_background=True,
        smooth=1.0,
    ):
        super().__init__()
        self.ce = nn.CrossEntropyLoss(weight=class_weights)
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.ignore_background = ignore_background
        self.smooth = smooth

    def forward(self, logits, target):
        prob = logits.softmax(1)
        oh = F.one_hot(target, logits.shape[1]).permute(0, 3, 1, 2).float()
        tp = (prob * oh).sum((0, 2, 3))
        fp = (prob * (1 - oh)).sum((0, 2, 3))
        fn = ((1 - prob) * oh).sum((0, 2, 3))
        tversky = (tp + self.smooth) / (tp + self.alpha * fp + self.beta * fn + self.smooth)
        ft = (1.0 - tversky) ** self.gamma
        start = 1 if self.ignore_background else 0
        return self.ce(logits, target) + ft[start:].mean()


def build_loss(
    name,
    class_weights=None,
    *,
    dice_w=0.5,
    dice_weighted=False,
    ignore_background=False,
    tversky=(0.3, 0.7, 1.3333),
):
    """Construct the segmentation loss selected on the CLI.

    ``ce_dice`` with defaults reproduces the original recipe (and is what the
    baseline control uses); ``focal_tversky`` is the opt-in minority-recall
    variant. Fails closed on an unknown name rather than silently defaulting.
    """
    if name == "ce_dice":
        return SegLoss(
            class_weights,
            dice_w=dice_w,
            dice_weighted=dice_weighted,
            ignore_background=ignore_background,
        )
    if name == "focal_tversky":
        a, b, g = tversky
        return FocalTverskyLoss(class_weights, alpha=a, beta=b, gamma=g, ignore_background=True)
    raise SystemExit(f"unknown --loss {name!r}; choose from {LOSSES}")


class ConfMat:
    def __init__(self, n=NUM_CLASSES):
        self.n, self.m = n, np.zeros((n, n), dtype=np.int64)

    def update(self, pred, gt):
        p, g = pred.flatten(), gt.flatten()
        self.m += np.bincount(g * self.n + p, minlength=self.n**2).reshape(self.n, self.n)

    def iou(self):
        """Per-class IoU (NaN where a class never appears in gt or pred), the
        mean over PRESENT classes, and the explicit list of absent class names.
        The absent list is returned so callers report dropped classes rather
        than silently inflating mIoU via np.nanmean (deployment roadmap Gate 4,
        RiceSEG repair #4)."""
        tp = np.diag(self.m).astype(np.float64)
        denom = self.m.sum(0) + self.m.sum(1) - tp
        iou = np.where(denom > 0, tp / np.maximum(denom, 1), np.nan)
        absent = [CLASS_NAMES[i] for i in range(self.n) if np.isnan(iou[i])]
        miou = float(np.nanmean(iou)) if np.any(~np.isnan(iou)) else float("nan")
        return iou, miou, absent


# ================================================================ selection / schedule
def stability_stats(history, window=5, class_names=CLASS_NAMES):
    """Mean/std of mIoU and per-class IoU over the final ``window`` epochs.

    Pure (no torch, no IO) so it is unit-testable, and the single source of
    truth: ``baseline_seg_control`` re-imports this rather than redefining it, so
    the pretraining run and the control report stability the same way. Classes
    absent from an epoch are recorded as ``None`` by the training loop and are
    skipped here rather than counted as zero (which would fabricate a low score
    for a class that simply did not appear in that epoch's validation pass).
    """
    if not history:
        return {}
    tail = history[-max(1, int(window)) :]
    mious = [h["miou"] for h in tail if h.get("miou") is not None and not np.isnan(h["miou"])]
    out = {
        "window": len(tail),
        "epochs": [h["epoch"] for h in tail],
        "miou_mean": float(np.mean(mious)) if mious else None,
        "miou_std": float(np.std(mious)) if mious else None,
        "per_class": {},
    }
    for name in class_names:
        vals = [h["per_class_iou"].get(name) for h in tail]
        vals = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
        out["per_class"][name] = {
            "mean": float(np.mean(vals)) if vals else None,
            "std": float(np.std(vals)) if vals else None,
            "min": float(np.min(vals)) if vals else None,
            "max": float(np.max(vals)) if vals else None,
            "n": len(vals),
        }
    return out


def selection_score(per_class_iou, select_classes):
    """Mean IoU over the target classes present this epoch, or ``None`` if none
    of them appeared. ``per_class_iou`` maps class name -> float|None exactly as
    the training history stores it. This is the signal used to export the
    backbone by the safety-critical minority classes instead of a
    background-dominated overall mIoU.
    """
    vals = [per_class_iou.get(c) for c in select_classes]
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not vals:
        return None
    return float(np.mean(vals))


def best_by_selection(
    history,
    metric="minority",
    select_classes=("weeds", "duckweed", "senescent"),
    ema_beta=0.6,
):
    """Pure, causal choice of the epoch whose weights should be exported.

    ``metric='miou'``     — original behaviour: argmax of the single-epoch
                            present-class mIoU. Kept so ``--select-metric miou``
                            reproduces prior runs (and drives the overfit gate).
    ``metric='minority'`` — EMA-smoothed mean IoU over ``select_classes``. This
                            resists the single-epoch weed swings (0.11–0.34 while
                            loss fell smoothly) that made the old argmax export a
                            noisy peak. Epochs where no target class is present
                            are skipped and the EMA is carried forward.

    Causal (uses only epochs up to each point), so replaying it over the growing
    history in the training loop selects exactly the epoch this returns over the
    full history. Returns ``{'best_epoch','best_score','metric','eligible_epochs'}``
    or ``None`` when no epoch is scorable (caller falls back to mIoU).
    """
    if not history:
        return None
    if metric == "miou":
        best = None
        for h in history:
            m = h.get("miou")
            if m is None or (isinstance(m, float) and np.isnan(m)):
                continue
            if best is None or m > best["best_score"]:
                best = {"best_epoch": h["epoch"], "best_score": float(m)}
        return {**best, "metric": "miou", "eligible_epochs": len(history)} if best else None
    ema, best, eligible = None, None, 0
    for h in history:
        raw = selection_score(h.get("per_class_iou", {}), select_classes)
        if raw is None:
            continue
        eligible += 1
        ema = raw if ema is None else ema_beta * ema + (1 - ema_beta) * raw
        if best is None or ema > best["best_score"]:
            best = {"best_epoch": h["epoch"], "best_score": float(ema)}
    return {**best, "metric": "minority", "eligible_epochs": eligible} if best else None


def build_param_groups(model, base_lr, backbone_mult=1.0):
    """Optimiser param groups. With ``backbone_mult == 1.0`` (default) this is a
    single group at ``base_lr`` — identical to the original AdamW over
    ``model.parameters()``. A value < 1.0 gives the (pre)trained backbone a
    smaller step than the freshly-initialised decoder/head (discriminative LR).
    """
    if backbone_mult == 1.0:
        return [{"params": [p for p in model.parameters() if p.requires_grad], "lr": base_lr}]
    bb, other = [], []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        (bb if name.startswith("backbone.") else other).append(p)
    groups = []
    if bb:
        groups.append({"params": bb, "lr": base_lr * backbone_mult})
    if other:
        groups.append({"params": other, "lr": base_lr})
    return groups


def build_scheduler(
    optimizer, epochs, warmup_epochs, base_lr, eta_min_ratio=0.01, warmup_start=0.01
):
    """Cosine anneal to ``base_lr * eta_min_ratio``, optionally preceded by a
    linear warmup. Stepped once per epoch. With ``warmup_epochs == 0`` (default)
    this is exactly ``CosineAnnealingLR(T_max=epochs, eta_min=base_lr*0.01)`` —
    the original schedule. A short warmup lets the reinitialised head settle
    before the backbone takes full-size steps, damping the early weed-IoU swing.
    """
    from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR, SequentialLR

    eta_min = base_lr * eta_min_ratio
    warmup_epochs = max(0, int(warmup_epochs))
    if warmup_epochs == 0:
        return CosineAnnealingLR(optimizer, T_max=epochs, eta_min=eta_min)
    warmup = LinearLR(
        optimizer, start_factor=warmup_start, end_factor=1.0, total_iters=warmup_epochs
    )
    cosine = CosineAnnealingLR(optimizer, T_max=max(1, epochs - warmup_epochs), eta_min=eta_min)
    return SequentialLR(optimizer, [warmup, cosine], milestones=[warmup_epochs])


# ================================================================ overfit gate
def _overfit_output_path(base_out):
    """Return an isolated temp path for the overfit sanity run so it can never
    overwrite the production backbone (`base_out`). The audit found the notebook
    passed the production path into the gate, so a gate-only or failed run could
    leave an 8-image-overfit backbone at the real path (Section 9.4)."""
    import tempfile

    fd, path = tempfile.mkstemp(prefix="riceseg_overfit_", suffix=".pth")
    os.close(fd)
    return Path(path)


def _enforce_overfit_gate(best_miou, threshold):
    """Fail closed if the overfit sanity run did not reach its preregistered
    mIoU. The old gate always continued regardless of score (Section 9.4)."""
    if best_miou < threshold:
        raise SystemExit(
            f"[gate] OVERFIT FAILED: best mIoU {best_miou:.4f} < threshold "
            f"{threshold:.4f}. The preprocessing/model/loss path is broken; "
            "fix it before any full pretraining run."
        )
    print(f"[gate] OVERFIT PASSED: best mIoU {best_miou:.4f} >= {threshold:.4f}")


def _stratified_overfit_subset(pairs, n, num_classes=NUM_CLASSES, scan_cap=512):
    """Pick tiles that together cover all classes so the overfit mIoU is a
    stable ``num_classes``-class score. The audit noted the first 8 sorted tiles
    contain no duckweed, so ``np.nanmean`` silently drops that class and inflates
    the gate (Section 9.4).

    Coverage is selected **first** and never truncated away: the previous
    implementation appended a class-covering tile past ``n`` and then returned
    ``chosen[:n]``, discarding the very tile it had scanned for (on RiceSEG the
    only duckweed tile in range sits at scan index 360 and was dropped every
    time). The subset may therefore exceed ``n`` when covering every class needs
    more tiles; that is deliberate — a stable denominator matters more than an
    exact count. Classes absent from the whole scan are reported, not hidden.
    """
    from PIL import Image

    def _classes(pair):
        return set(np.unique(np.asarray(Image.open(pair["label"]))).tolist())

    # Pass 1 — greedy set cover: keep only tiles that contribute a new class.
    covering, seen = [], set()
    wanted = set(range(num_classes))
    for p in pairs[:scan_cap]:
        if seen >= wanted:
            break
        if _classes(p) - seen:
            covering.append(p)
            seen |= _classes(p)

    missing = sorted(wanted - seen)
    if missing:
        names = [CLASS_NAMES[i] for i in missing]
        print(
            f"[gate] WARNING: class(es) {names} absent from the first {scan_cap} tiles; "
            f"the overfit mIoU is a {len(seen)}-class score and its denominator "
            "may vary between epochs."
        )

    # Pass 2 — pad up to n with the cheapest (earliest) tiles not already taken.
    chosen = list(covering)
    taken = {id(p) for p in chosen}
    for p in pairs:
        if len(chosen) >= n:
            break
        if id(p) not in taken:
            chosen.append(p)
            taken.add(id(p))
    return chosen


def _overfit_epochs(n_tiles, batch_size, requested_epochs, min_steps=1000, min_epochs=60):
    """Epoch count giving the overfit gate a real optimisation budget.

    The gate previously floored *epochs* at 60. With 8 tiles at batch 4 and
    ``drop_last`` that is 2 optimiser steps per epoch — 120 AdamW steps at
    ``lr 3e-4`` under a cosine decay, far too few to memorise 8 images, so the
    run plateaued mid-range and the gate failed for want of training rather than
    for a broken pipeline. Floor the *steps* instead; the schedule still spans
    exactly ``epochs`` so the cosine is unchanged in shape.
    """
    steps_per_epoch = max(1, n_tiles // batch_size if n_tiles > batch_size else 1)
    needed = -(-min_steps // steps_per_epoch)  # ceil
    return max(requested_epochs, min_epochs, needed)


# ================================================================ gates
def self_test():
    """No data needed. Asserts seg-model backbone keys == WeedDet backbone
    keys and round-trips export -> load_riceseg_backbone."""
    import tempfile

    seg = RiceSegModel()
    det = wd.WeedDet(num_classes=1, anchor_base_scale=3, lsc_k=7, use_atss=True)
    seg_bk = {k for k in seg.state_dict() if k.startswith("backbone.")}
    det_bk = {k for k in det.state_dict() if k.startswith("backbone.")}
    assert (
        seg_bk == det_bk
    ), f"KEY MISMATCH: {len(seg_bk - det_bk)} only-seg, {len(det_bk - seg_bk)} only-det"
    print(f"[self-test] backbone keys identical: {len(seg_bk)} tensors")
    with torch.no_grad():
        y = seg(torch.randn(1, 3, 64, 64))
    assert y.shape == (1, NUM_CLASSES, 64, 64), y.shape
    with tempfile.TemporaryDirectory() as td:
        pth = os.path.join(td, "bk.pth")
        export_backbone(seg, pth)
        n = load_riceseg_backbone(det, pth)
    print(f"[self-test] export->load round-trip OK ({n} tensors). PASS")


# ================================================================ train
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--out", default="riceseg_backbone.pth")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--img-size", type=int, default=512)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--holdout-country", default=None)
    ap.add_argument(
        "--no-imagenet", action="store_true", help="skip ImageNet warm-start of the compatible 92%"
    )
    ap.add_argument("--include-fpn", action="store_true")
    # --- item 1: recipe / loader parity (no more hard-coded num_workers) ---
    ap.add_argument("--num-workers", type=int, default=2)
    # --- item 2: robust checkpoint selection ---
    ap.add_argument(
        "--select-metric",
        choices=("minority", "miou"),
        default="minority",
        help="which epoch to export: 'minority' = EMA-smoothed mean IoU over "
        "--select-classes (resists single-epoch weed swings); 'miou' = old "
        "single-epoch present-class mIoU (reproduces prior runs). Overfit runs "
        "always use 'miou' so the gate is unchanged.",
    )
    ap.add_argument(
        "--select-classes",
        default="weeds,duckweed,senescent",
        help="comma-separated target classes for --select-metric minority",
    )
    ap.add_argument(
        "--select-ema", type=float, default=0.6, help="EMA beta for the minority selection score"
    )
    # --- item 3: loss / LR levers for the hard classes (default = old recipe) ---
    ap.add_argument("--loss", choices=LOSSES, default="ce_dice")
    ap.add_argument(
        "--dice-weighted",
        action="store_true",
        help="weight the Dice term by the class weights (ce_dice only)",
    )
    ap.add_argument(
        "--dice-ignore-bg",
        action="store_true",
        help="exclude background from the Dice term (ce_dice only)",
    )
    ap.add_argument("--tversky-alpha", type=float, default=0.3, help="FP weight (focal_tversky)")
    ap.add_argument("--tversky-beta", type=float, default=0.7, help="FN weight (focal_tversky)")
    ap.add_argument("--tversky-gamma", type=float, default=1.3333, help="focusing (focal_tversky)")
    ap.add_argument(
        "--warmup-epochs", type=int, default=0, help="linear LR warmup before cosine (0 = off)"
    )
    ap.add_argument(
        "--backbone-lr-mult",
        type=float,
        default=1.0,
        help="LR multiplier for backbone params vs head (1.0 = single group)",
    )
    ap.add_argument(
        "--overfit",
        type=int,
        default=0,
        help="sanity gate: train on N tiles, expect high mIoU "
        "(use --batch-size 4 with --overfit 8)",
    )
    ap.add_argument(
        "--overfit-min-miou",
        type=float,
        default=0.80,
        help="preregistered mIoU the overfit gate must reach or the " "run fails (exit 2)",
    )
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    assert args.data_root, "--data-root required (or use --self-test)"

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[setup] device={device}")

    pairs = scan_riceseg(args.data_root)
    countries = sorted({p["country"] for p in pairs})
    print(f"[data] {len(pairs)} tiles | countries: {countries}")

    # Fail loudly if a country holdout names a country the archive does not
    # contain (roadmap Gate 4, RiceSEG repair #2). The old parser labelled every
    # tile "global rice segmentation", so any real country silently held out 0.
    if args.holdout_country and args.holdout_country.lower() not in {c.lower() for c in countries}:
        raise SystemExit(
            f"--holdout-country {args.holdout_country!r} is not present; "
            f"available countries: {countries}"
        )

    select_classes = [c.strip() for c in args.select_classes.split(",") if c.strip()]
    unknown = [c for c in select_classes if c not in CLASS_NAMES]
    if unknown:
        raise SystemExit(
            f"--select-classes has unknown class(es) {unknown}; choose from {CLASS_NAMES}"
        )
    # The overfit gate is a mIoU sanity check; keep its selection unchanged.
    select_metric = "miou" if args.overfit else args.select_metric

    if args.overfit:
        # Stratified so all six classes appear (else duckweed NaN inflates mIoU),
        # and exported to an isolated temp path that can never clobber args.out.
        train_p = val_p = _stratified_overfit_subset(pairs, args.overfit)
        epochs = _overfit_epochs(len(train_p), args.batch_size, args.epochs)
        out_path = _overfit_output_path(args.out)
        steps = epochs * max(1, len(train_p) // args.batch_size)
        print(
            f"[gate] OVERFIT-{args.overfit}: {len(train_p)} tiles, {epochs} epochs "
            f"(~{steps} steps); must reach mIoU >= {args.overfit_min_miou:.2f}; "
            f"isolated export -> {out_path} (production path {args.out} untouched)"
        )
    else:
        train_p, val_p = split_pairs(pairs, args.val_ratio, args.seed, args.holdout_country)
        epochs = args.epochs
        out_path = Path(args.out)
        print(
            f"[split] train {len(train_p)} / val {len(val_p)} "
            f"(group-aware by source photo; 0 source overlap)"
        )

    # Create the export dir up front so a run cannot train for hours and then
    # die at the first checkpoint write (baseline_seg_control does the same).
    out_path.parent.mkdir(parents=True, exist_ok=True)

    weights = compute_class_weights(train_p).to(device)
    # Loader config mirrors baseline_seg_control so the two runs share it: keep
    # the worker pool alive across epochs (persistent_workers) instead of
    # respawning it every boundary, and expose num_workers instead of a
    # hard-coded 2 (CLAUDE.md 3.3).
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

    model = RiceSegModel().to(device)
    imagenet_coverage = None
    if not args.no_imagenet:
        # Fail closed on a silent ImageNet miss: a torchvision fetch failure
        # returns (0, 0) and would otherwise turn a labelled "ImageNet->RiceSEG"
        # run into an unlabelled scratch run (audit P1-9 / roadmap repair #8).
        n_loaded, n_missed = wd.load_imagenet_backbone(model)
        n_backbone = sum(1 for k in model.state_dict() if k.startswith("backbone."))
        imagenet_coverage = {
            "loaded": int(n_loaded),
            "missed": int(n_missed),
            "backbone_total": int(n_backbone),
        }
        if n_loaded == 0:
            raise SystemExit(
                "[imagenet] load returned 0 tensors — refusing to run a scratch "
                "job mislabelled as ImageNet->RiceSEG. Use --no-imagenet to run "
                "true scratch, or fix connectivity/weights."
            )
        print(
            f"[imagenet] warm-started {n_loaded}/{n_backbone} backbone tensors "
            f"(the custom stem + layer1.0 stay random by design)"
        )
        # NOTE: no BN freezing here — the whole point is retraining ALL BN in-domain.
    else:
        print("[imagenet] skipped (--no-imagenet): true random->RiceSEG condition")
    crit = build_loss(
        args.loss,
        weights,
        dice_weighted=args.dice_weighted,
        ignore_background=args.dice_ignore_bg,
        tversky=(args.tversky_alpha, args.tversky_beta, args.tversky_gamma),
    )
    opt = torch.optim.AdamW(
        build_param_groups(model, args.lr, args.backbone_lr_mult), lr=args.lr, weight_decay=1e-4
    )
    sched = build_scheduler(opt, epochs, args.warmup_epochs, args.lr)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    print(
        f"[loss] {args.loss} (dice_weighted={args.dice_weighted}, "
        f"ignore_bg={args.dice_ignore_bg}) | [lr] warmup={args.warmup_epochs} "
        f"backbone_mult={args.backbone_lr_mult} | [select] {select_metric}"
        + (f" over {select_classes} ema={args.select_ema}" if select_metric == "minority" else "")
    )

    best = -1.0
    best_epoch, best_iou_vec, best_absent = 0, None, []
    best_sel_score = None
    exported_any = False
    history = []
    for ep in range(1, epochs + 1):
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
        line = f"epoch {ep:02d}/{epochs}  loss={avg_loss:.4f}  mIoU={miou:.4f}  " + " ".join(
            f"{nm}={v:.2f}" for nm, v in zip(CLASS_NAMES, iou)
        )
        if absent:
            # Explicit, not silent: mIoU above is the mean over PRESENT classes.
            line += f'  [absent: {",".join(absent)}]'
        # Export by the selection metric, not raw single-epoch mIoU. Replaying
        # the causal selector over the history so far yields the same epoch it
        # would over the full history, so the running best is exact.
        sel = best_by_selection(history, select_metric, tuple(select_classes), args.select_ema)
        if sel and sel["best_epoch"] == ep:
            best, best_epoch, best_iou_vec, best_absent = miou, ep, iou, absent
            best_sel_score = sel["best_score"]
            export_backbone(model, out_path, include_fpn=args.include_fpn)
            if not args.overfit:
                save_full_checkpoint(
                    Path(str(out_path) + ".fullckpt.pth"),
                    model,
                    opt,
                    sched,
                    ep,
                    best,
                    vars(args),
                    history,
                )
            exported_any = True
            line += f"  * exported ({select_metric}={sel['best_score']:.4f})"
        print(line, flush=True)

    if not exported_any:
        # The selection metric never scored an epoch (target classes never
        # appeared in validation). Export the final model so a checkpoint always
        # exists, and say so loudly rather than silently shipping nothing.
        print(
            f"[warn] --select-metric {select_metric} never scored an epoch "
            f"(classes {select_classes} absent from val); exporting FINAL epoch."
        )
        best, best_epoch, best_iou_vec, best_absent = miou, epochs, iou, absent
        best_sel_score = None
        export_backbone(model, out_path, include_fpn=args.include_fpn)
        if not args.overfit:
            save_full_checkpoint(
                Path(str(out_path) + ".fullckpt.pth"),
                model,
                opt,
                sched,
                epochs,
                best,
                vars(args),
                history,
            )

    if args.overfit:
        _enforce_overfit_gate(best, args.overfit_min_miou)
        print(f"\nOverfit sanity artifact (not for reuse): {out_path}")
        return

    # Immutable run record beside the exported backbone (roadmap Gate 1/Gate 4 #7).
    manifest = {
        "schema_version": "agrinav.riceseg_pretrain.run.v1",
        "seed": args.seed,
        "git_commit": _git_commit(Path(__file__).resolve().parent),
        "environment": _env_versions(),
        "device": str(device),
        "config": vars(args),
        "data": {
            "data_root": str(args.data_root),
            "tiles": len(pairs),
            "countries": countries,
            "train_tiles": len(train_p),
            "val_tiles": len(val_p),
            "holdout_country": args.holdout_country,
        },
        "imagenet_coverage": imagenet_coverage,
        "selection": {
            "metric": select_metric,
            "select_classes": select_classes,
            "ema_beta": args.select_ema,
            "best_epoch": best_epoch,
            "best_score": best_sel_score,
        },
        "loss": {
            "name": args.loss,
            "dice_weighted": args.dice_weighted,
            "ignore_background": args.dice_ignore_bg,
            "tversky": [args.tversky_alpha, args.tversky_beta, args.tversky_gamma],
        },
        "lr_schedule": {
            "warmup_epochs": args.warmup_epochs,
            "backbone_lr_mult": args.backbone_lr_mult,
        },
        "stability": stability_stats(history, 5),
        "best": {
            "epoch": best_epoch,
            "miou_present_classes": best,
            "per_class_iou": {
                nm: (None if best_iou_vec is None or np.isnan(v) else float(v))
                for nm, v in zip(
                    CLASS_NAMES,
                    best_iou_vec if best_iou_vec is not None else [np.nan] * NUM_CLASSES,
                )
            },
            "absent_classes": best_absent,
        },
        "history": history,
        "backbone_export": {
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "include_fpn": args.include_fpn,
        },
        "full_checkpoint": str(out_path) + ".fullckpt.pth",
    }
    write_run_manifest(str(out_path) + ".manifest.json", manifest)

    print(f"\nDone. Best mIoU {best:.4f} at epoch {best_epoch} -> {out_path}")
    if best_absent:
        print(
            f"[warn] classes absent from validation at best epoch: {best_absent} "
            "(mIoU is over present classes only)"
        )
    print(
        "Load into WeedDet with load_riceseg_backbone(); keep BN trainable "
        "(or freeze_backbone_bn) — NEVER apply_bn_policy."
    )


if __name__ == "__main__":
    main()
