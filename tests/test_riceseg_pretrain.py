"""Synthetic correctness tests for training/riceseg_pretrain.py.

These cover the transfer-learning defects called out in the July 20 deep audit
(docs/audits/2026-07-20/AGRINAV_FULL_DEEP_AUDIT_2026-07-20.md), specifically the
Section 17.1 acceptance gates:

  * RiceSEG country/site parsing returns China, India, Japan, Philippines, and
    Tanzania for the supplied archive layout (audit Section 9.4);
  * unknown mask values fail rather than clip (audit Section 9.4);
  * the RiceSEG overfit gate cannot write the production backbone path and fails
    when its threshold is missed (audit Section 9.4 / 17.1);
  * backbone loading requires the full expected key set (audit Section 9.4).

The tests are deterministic and CPU-only.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import agrinav.training.riceseg_pretrain as rp
from agrinav.training.riceseg_pretrain import (
    CLASS_NAMES,
    NUM_CLASSES,
    ConfMat,
    RiceSegDataset,
    RiceSegModel,
    _enforce_overfit_gate,
    _overfit_epochs,
    _overfit_output_path,
    _stratified_overfit_subset,
    export_backbone,
    load_riceseg_backbone,
    parse_country_site,
    scan_riceseg,
    sha256_file,
)


def _seg_history(weeds, mious=None):
    """History rows shaped like the training loop emits (weeds IoU varied, other
    classes fixed) for exercising the checkpoint-selection logic."""
    out = []
    for i, w in enumerate(weeds):
        out.append(
            {
                "epoch": i + 1,
                "miou": 0.5 if mious is None else mious[i],
                "per_class_iou": {
                    "background": 0.9,
                    "green_veg": 0.85,
                    "senescent": 0.35,
                    "panicle": 0.7,
                    "weeds": w,
                    "duckweed": 0.35,
                },
                "absent_classes": [],
            }
        )
    return out


# The supplied RiceSEG archive extracts to a single wrapper directory that then
# contains one directory per country; some countries add a site level.
WRAPPER = "global rice segmentation"
LAYOUT = {
    ("China", "GD"): "IMG_5014_subset_overlap_0_4",
    ("China", "HN"): "DSCF0083_subset_overlap_3_0",
    ("Japan", "TKO_1"): "2014_0712_080213_subset_overlap_0_0",
    ("India", None): "IMG_0560_subset_overlap_1_1",
    ("Philippines", None): "00864_subset_overlap_0_1",
    ("Tanzania", None): "103_subset_overlap_1_0",
}


def _write_pair(root: Path, country: str, site, stem: str, mask_values=(0, 1, 4)):
    parent = root / WRAPPER / country
    if site is not None:
        parent = parent / site
    rgb_dir = parent / "rgb"
    lab_dir = parent / "label"
    rgb_dir.mkdir(parents=True, exist_ok=True)
    lab_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 120, 30)).save(rgb_dir / f"{stem}.jpg")
    mask = np.zeros((8, 8), dtype=np.uint8)
    for i, v in enumerate(mask_values):
        mask[i % 8, :] = v
    Image.fromarray(mask, mode="L").save(lab_dir / f"{stem}.png")


def _build_archive(root: Path):
    for (country, site), stem in LAYOUT.items():
        _write_pair(root, country, site, stem)


class CountrySiteParsingTests(unittest.TestCase):
    def test_parse_country_site_handles_both_layout_shapes(self):
        root = Path("/data/RiceSEG")
        with_site = root / WRAPPER / "China" / "GD" / "rgb" / "IMG_5014.jpg"
        no_site = root / WRAPPER / "India" / "rgb" / "IMG_0560.jpg"
        self.assertEqual(parse_country_site(with_site, root), ("China", "GD"))
        self.assertEqual(parse_country_site(no_site, root), ("India", None))

    def test_scan_riceseg_returns_all_five_countries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_archive(root)
            pairs = scan_riceseg(root)
            countries = {p["country"] for p in pairs}
            self.assertEqual(
                countries,
                {"China", "India", "Japan", "Philippines", "Tanzania"},
            )
            # The wrapper directory must never leak into the country field.
            self.assertNotIn(WRAPPER, countries)

    def test_scan_riceseg_parses_site_or_none(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_archive(root)
            by_country = {}
            for p in pairs_by_country(scan_riceseg(root)):
                by_country.setdefault(p["country"], set()).add(p.get("site"))
            self.assertIn("GD", by_country["China"])
            self.assertEqual(by_country["India"], {None})

    def test_country_holdout_split_is_now_reachable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_archive(root)
            pairs = scan_riceseg(root)
            train, val = rp.split_pairs(pairs, holdout_country="Tanzania")
            self.assertTrue(val, "holdout country must select at least one tile")
            self.assertTrue(all(p["country"] == "Tanzania" for p in val))
            self.assertTrue(all(p["country"] != "Tanzania" for p in train))


def pairs_by_country(pairs):
    return pairs


class MaskValidationTests(unittest.TestCase):
    def _dataset_with_mask(self, td: Path, values):
        rgb = td / "img.jpg"
        lab = td / "mask.png"
        Image.new("RGB", (8, 8), (0, 0, 0)).save(rgb)
        arr = np.zeros((8, 8), dtype=np.uint8)
        arr[0, : len(values)] = values
        Image.fromarray(arr, mode="L").save(lab)
        pair = {
            "rgb": str(rgb),
            "label": str(lab),
            "country": "China",
            "site": "GD",
            "source": "China/img",
        }
        return RiceSegDataset([pair], img_size=8)

    def test_valid_mask_values_pass(self):
        with tempfile.TemporaryDirectory() as td:
            ds = self._dataset_with_mask(Path(td), list(range(NUM_CLASSES)))
            x, y = ds[0]
            self.assertEqual(tuple(y.shape), (8, 8))
            self.assertTrue(int(y.max()) < NUM_CLASSES)

    def test_unknown_mask_value_raises(self):
        with tempfile.TemporaryDirectory() as td:
            ds = self._dataset_with_mask(Path(td), [0, 1, 200])
            with self.assertRaises(ValueError):
                _ = ds[0]

    def test_ignore_index_is_allowed_when_configured(self):
        with tempfile.TemporaryDirectory() as td:
            rgb = Path(td) / "img.jpg"
            lab = Path(td) / "mask.png"
            Image.new("RGB", (8, 8), (0, 0, 0)).save(rgb)
            arr = np.zeros((8, 8), dtype=np.uint8)
            arr[0, 0] = 255
            Image.fromarray(arr, mode="L").save(lab)
            pair = {
                "rgb": str(rgb),
                "label": str(lab),
                "country": "China",
                "site": "GD",
                "source": "China/img",
            }
            ds = RiceSegDataset([pair], img_size=8, ignore_index=255)
            _, y = ds[0]
            self.assertEqual(int((y == 255).sum()), 1)


class BackboneLoadingTests(unittest.TestCase):
    def test_complete_backbone_roundtrips(self):
        seg = RiceSegModel()
        det = rp.wd.WeedDet(num_classes=1, anchor_base_scale=3, lsc_k=7, use_atss=True)
        with tempfile.TemporaryDirectory() as td:
            pth = Path(td) / "bk.pth"
            export_backbone(seg, pth)
            n = load_riceseg_backbone(det, pth, verbose=False)
            self.assertGreater(n, 150)

    def test_incomplete_backbone_is_rejected(self):
        seg = RiceSegModel()
        det = rp.wd.WeedDet(num_classes=1, anchor_base_scale=3, lsc_k=7, use_atss=True)
        with tempfile.TemporaryDirectory() as td:
            pth = Path(td) / "bk.pth"
            sd = export_backbone(seg, pth)
            # Drop a handful of backbone tensors to simulate a partial export.
            dropped = dict(sd)
            for k in list(dropped)[:5]:
                del dropped[k]
            torch.save(dropped, pth)
            with self.assertRaises(ValueError):
                load_riceseg_backbone(det, pth, verbose=False)


class OverfitGateTests(unittest.TestCase):
    def test_overfit_output_is_isolated_from_production(self):
        production = Path("riceseg_backbone.pth")
        isolated = _overfit_output_path(production)
        self.assertNotEqual(isolated.resolve(), production.resolve())
        self.assertNotEqual(isolated.name, production.name)

    def test_overfit_gate_fails_below_threshold(self):
        with self.assertRaises(SystemExit):
            _enforce_overfit_gate(0.10, 0.80)

    def test_overfit_gate_passes_at_or_above_threshold(self):
        # Must not raise.
        _enforce_overfit_gate(0.85, 0.80)


class OverfitSubsetTests(unittest.TestCase):
    """The subset must keep the rare class it scanned for.

    Mirrors the real failure: on RiceSEG the only in-range duckweed tile sits
    far past ``n``, and the old ``chosen[:n]`` truncation discarded it, so the
    gate's mIoU denominator flipped between 5 and 6 classes across epochs.
    """

    def _pairs(self, tmp, class_sets):
        from PIL import Image

        pairs = []
        for i, classes in enumerate(class_sets):
            path = Path(tmp) / f"label_{i:03d}.png"
            arr = np.zeros((4, 4), dtype=np.uint8)
            for j, c in enumerate(sorted(classes)):
                arr.flat[j] = c
            Image.fromarray(arr).save(path)
            pairs.append({"rgb": path, "label": path})
        return pairs

    def test_rare_class_far_past_n_is_retained(self):
        # 8 common tiles, then one carrying the rare class -> must survive.
        common = [{0, 1, 2, 3}] * 8
        rare = [{0, 5}]
        with tempfile.TemporaryDirectory() as tmp:
            pairs = self._pairs(tmp, common + rare)
            chosen = _stratified_overfit_subset(pairs, 8, num_classes=NUM_CLASSES)
            covered = set()
            for p in chosen:
                covered |= set(np.unique(np.asarray(Image.open(p["label"]))).tolist())
        self.assertIn(5, covered, "rare class was truncated away (the original bug)")

    def test_pads_up_to_n_when_coverage_is_cheap(self):
        with tempfile.TemporaryDirectory() as tmp:
            pairs = self._pairs(tmp, [set(range(NUM_CLASSES))] + [{0, 1}] * 10)
            chosen = _stratified_overfit_subset(pairs, 8, num_classes=NUM_CLASSES)
        self.assertEqual(len(chosen), 8)

    def test_absent_class_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            pairs = self._pairs(tmp, [{0, 1}] * 4)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                _stratified_overfit_subset(pairs, 4, num_classes=NUM_CLASSES)
        self.assertIn("WARNING", buf.getvalue())


class OverfitBudgetTests(unittest.TestCase):
    def test_step_budget_is_floored_not_just_epochs(self):
        # 8 tiles at batch 4 -> 2 steps/epoch; 60 epochs would be only 120 steps.
        epochs = _overfit_epochs(8, 4, requested_epochs=30)
        self.assertGreaterEqual(epochs * (8 // 4), 1000)

    def test_explicit_larger_epoch_request_is_honoured(self):
        self.assertGreaterEqual(_overfit_epochs(8, 4, requested_epochs=5000), 5000)

    def test_batch_larger_than_subset_does_not_divide_by_zero(self):
        self.assertGreater(_overfit_epochs(4, 8, requested_epochs=1), 0)


class MetricReportingTests(unittest.TestCase):
    def test_absent_classes_are_reported_not_silently_dropped(self):
        # Only classes 0 and 1 ever appear; the other four must be reported
        # absent rather than silently excluded from the headline mIoU.
        cm = ConfMat()
        pred = np.array([[0, 1], [0, 1]])
        gt = np.array([[0, 1], [0, 1]])
        cm.update(pred, gt)
        iou, miou, absent = cm.iou()
        self.assertEqual(set(absent), set(CLASS_NAMES[2:]))
        self.assertAlmostEqual(miou, 1.0, places=6)  # over present classes only
        self.assertEqual(len(iou), NUM_CLASSES)

    def test_all_classes_present_reports_no_absent(self):
        cm = ConfMat()
        diag = np.arange(NUM_CLASSES)
        cm.update(diag, diag)
        _, _, absent = cm.iou()
        self.assertEqual(absent, [])


class HashHelperTests(unittest.TestCase):
    def test_sha256_file_is_stable_and_content_sensitive(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.bin"
            b = Path(td) / "b.bin"
            a.write_bytes(b"agrinav")
            b.write_bytes(b"agrinav")
            self.assertEqual(sha256_file(a), sha256_file(b))
            b.write_bytes(b"agrinav2")
            self.assertNotEqual(sha256_file(a), sha256_file(b))


class SelectionScoreTests(unittest.TestCase):
    def test_mean_over_present_target_classes(self):
        pc = {"weeds": 0.4, "duckweed": 0.2, "senescent": 0.6, "background": 0.9}
        self.assertAlmostEqual(
            rp.selection_score(pc, ["weeds", "duckweed", "senescent"]), 0.4, places=6
        )

    def test_none_when_no_target_present(self):
        pc = {"background": 0.9, "green_veg": 0.8, "weeds": None, "duckweed": None}
        self.assertIsNone(rp.selection_score(pc, ["weeds", "duckweed"]))

    def test_absent_target_is_skipped_not_zeroed(self):
        # duckweed absent must not drag the score to 0.25; it is simply skipped.
        pc = {"weeds": 0.5, "duckweed": None}
        self.assertAlmostEqual(rp.selection_score(pc, ["weeds", "duckweed"]), 0.5, places=6)


class BestBySelectionTests(unittest.TestCase):
    def test_empty_history_returns_none(self):
        self.assertIsNone(rp.best_by_selection([], "minority"))

    def test_miou_mode_is_single_epoch_argmax(self):
        h = _seg_history([0.2, 0.5, 0.2], mious=[0.50, 0.61, 0.55])
        sel = rp.best_by_selection(h, metric="miou")
        self.assertEqual(sel["best_epoch"], 2)
        self.assertEqual(sel["metric"], "miou")

    def test_minority_ema_rejects_isolated_spike(self):
        # weeds spikes at epoch 3 but is sustained high at 5-6; EMA must prefer
        # the sustained region, not the lone noisy peak.
        h = _seg_history([0.2, 0.2, 0.5, 0.2, 0.45, 0.5])
        sel = rp.best_by_selection(h, "minority", select_classes=("weeds",), ema_beta=0.6)
        self.assertEqual(sel["best_epoch"], 6)
        self.assertNotEqual(sel["best_epoch"], 3)

    def test_metrics_diverge_on_a_noisy_peak(self):
        # mIoU peaks at the same epoch the weed value spikes: the old metric
        # would export that noisy epoch, the new one would not. That divergence
        # is the entire reason for the fix.
        h = _seg_history([0.2, 0.2, 0.5, 0.2, 0.45, 0.5], mious=[0.5, 0.5, 0.62, 0.5, 0.55, 0.58])
        self.assertEqual(rp.best_by_selection(h, "miou")["best_epoch"], 3)
        self.assertEqual(rp.best_by_selection(h, "minority", ("weeds",), 0.6)["best_epoch"], 6)

    def test_none_when_targets_never_present(self):
        h = _seg_history([None, None])
        self.assertIsNone(rp.best_by_selection(h, "minority", ("weeds",)))


class LossTests(unittest.TestCase):
    def _batch(self):
        torch.manual_seed(0)
        return torch.randn(2, NUM_CLASSES, 8, 8), torch.randint(0, NUM_CLASSES, (2, 8, 8))

    def test_default_ce_dice_matches_legacy_formula(self):
        import torch.nn.functional as F

        logits, target = self._batch()
        ce = torch.nn.CrossEntropyLoss()(logits, target)
        prob = logits.softmax(1)
        oh = F.one_hot(target, NUM_CLASSES).permute(0, 3, 1, 2).float()
        inter = (prob * oh).sum((0, 2, 3))
        card = prob.sum((0, 2, 3)) + oh.sum((0, 2, 3))
        legacy = ce + 0.5 * (1.0 - ((2 * inter + 1.0) / (card + 1.0)).mean())
        self.assertAlmostEqual(float(rp.SegLoss()(logits, target)), float(legacy), places=5)

    def test_weighted_dice_changes_the_value(self):
        logits, target = self._batch()
        w = torch.tensor([0.5, 0.5, 1.0, 1.0, 8.0, 8.0])
        plain = float(rp.SegLoss(w)(logits, target))
        weighted = float(rp.SegLoss(w, dice_weighted=True)(logits, target))
        self.assertNotAlmostEqual(plain, weighted, places=4)

    def test_ignore_background_changes_the_value(self):
        logits, target = self._batch()
        full = float(rp.SegLoss()(logits, target))
        nobg = float(rp.SegLoss(ignore_background=True)(logits, target))
        self.assertNotAlmostEqual(full, nobg, places=5)

    def test_focal_tversky_is_a_finite_scalar(self):
        logits, target = self._batch()
        loss = rp.build_loss("focal_tversky")(logits, target)
        self.assertEqual(loss.dim(), 0)
        self.assertTrue(bool(torch.isfinite(loss)))

    def test_unknown_loss_name_fails_closed(self):
        with self.assertRaises(SystemExit):
            rp.build_loss("dice_only")


class ParamGroupTests(unittest.TestCase):
    def test_single_group_when_mult_is_one(self):
        groups = rp.build_param_groups(RiceSegModel(), 3e-4, 1.0)
        self.assertEqual(len(groups), 1)
        self.assertAlmostEqual(groups[0]["lr"], 3e-4)

    def test_discriminative_lr_splits_backbone_and_head(self):
        model = RiceSegModel()
        groups = rp.build_param_groups(model, 3e-4, 0.1)
        self.assertEqual(len(groups), 2)
        lrs = sorted(g["lr"] for g in groups)
        self.assertAlmostEqual(lrs[0], 3e-5)  # backbone (0.1x)
        self.assertAlmostEqual(lrs[1], 3e-4)  # head
        counted = sum(sum(p.numel() for p in g["params"]) for g in groups)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        self.assertEqual(counted, trainable)


class SchedulerTests(unittest.TestCase):
    def _opt(self, base_lr=1e-3):
        return torch.optim.AdamW(rp.build_param_groups(RiceSegModel(), base_lr, 1.0), lr=base_lr)

    def test_no_warmup_starts_at_base_lr(self):
        opt = self._opt()
        rp.build_scheduler(opt, epochs=10, warmup_epochs=0, base_lr=1e-3)
        self.assertAlmostEqual(opt.param_groups[0]["lr"], 1e-3, places=7)

    def test_warmup_starts_low_then_reaches_base(self):
        opt = self._opt()
        sched = rp.build_scheduler(opt, epochs=10, warmup_epochs=3, base_lr=1e-3, warmup_start=0.01)
        self.assertLess(opt.param_groups[0]["lr"], 1e-3)  # warm start
        for _ in range(3):
            opt.step()  # match real order (optimizer before scheduler)
            sched.step()
        self.assertAlmostEqual(opt.param_groups[0]["lr"], 1e-3, places=5)  # base after warmup

    def test_cosine_reaches_eta_min_floor(self):
        opt = self._opt()
        sched = rp.build_scheduler(opt, epochs=5, warmup_epochs=0, base_lr=1e-3, eta_min_ratio=0.01)
        for _ in range(5):
            opt.step()  # match real order (optimizer before scheduler)
            sched.step()
        self.assertLessEqual(opt.param_groups[0]["lr"], 1e-3 * 0.01 + 1e-9)


if __name__ == "__main__":
    unittest.main()
