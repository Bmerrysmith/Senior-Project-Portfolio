# Dataset card — curated RICE, phase-2 detector (rebuild of 2026-07-29)

This is the dataset the phase-2 detector trains on. It is **not** the dataset
described in `docs/detector_dataset_card.md` — that card documents the
RiceSEG-derived 245-image polygon set. Until 2026-07-29 this dataset had no card
at all; it existed only as a Drive ZIP and a paragraph in `docs/HANDOFF.md`, which
is how a mis-built archive went undetected through two training runs.

Portfolio claim boundaries: [`PORTFOLIO_RESULTS.md`](PORTFOLIO_RESULTS.md).

## Identity

| Field | Value |
|---|---|
| Name | curated RICE, phase-2 detector dataset |
| Version | rebuild 2026-07-29 |
| Task | 2-class object detection (boxes) |
| Classes | `rice_protect` (id 1), `weed_target` (id 2) |
| Built by | `agrinav data-build-rice-phase2 build` (`src/agrinav/data/build_rice_phase2.py`) |
| Source | `agrinav_intake_2026-07-21/deliverable/detection/RICE/` (local; not in Git) |
| Split manifest | `grouped_split.json`, sha256 `5d63a0d74310cbd22672b6fddc4f3e9f7f65ab084d79910b0c12264d3dba1862` |
| Grouping method (as recorded by the source) | grouped by capture-series family, 40-frame contiguous blocks, greedy weed-balanced 70/20/10 |

Emitted annotation hashes:

| File | sha256 |
|---|---|
| `annotations/instances_train.coco.json` | `5a20a1f50cb68eded8b948b064d8ed5bb3743fc7f18966b5f75cae2098d7dbdc` |
| `annotations/instances_valid.coco.json` | `cc33cee100dbacbf68d8184393f03714076b92731021f7445d2204ce087af78d` |
| `annotations/instances_test.coco.json` | `00269928f406a3bb8114112f0c3e52ca0c45eddeab7eb032363c4ee87ca82683` |
| `manifests/split_membership.json` | `4511367de372107cc73ff56630b6c3651e9cd579d701865a491937024227e55d` |
| `manifests/grouped_split.json` (vendored copy) | `5d63a0d74310cbd22672b6fddc4f3e9f7f65ab084d79910b0c12264d3dba1862` |

Packaged training archive (train + valid only; test excluded by `package`):

| Field | Value |
|---|---|
| File | `RICE_phase2_rebuild.zip` |
| Bytes | 644,892,580 |
| sha256 | `40eb6370f41eeb53333918cfbeb55d3696a848067e2c96a389a8e1508be3fd03` |
| Members | 2,327 |
| Verified | extracted and re-`preflight`ed clean on 2026-07-30: train 1,800 / 59,691, valid 518 / 15,226, `splits_absent: ["test"]` |

Repackaged on 2026-07-30 (previously 644,891,718 B, sha256 `57484b9d…f190db27`).
The only change is metadata: `manifests/provenance.json` carried a stale
`test_split_status: "BURNED -- see TEST_SPLIT_BURNED.md"`, and that notice file
was renamed `TEST_SPLIT_STATUS.md` when the verdict was corrected. **No image,
annotation, count or per-file hash changed** — every sha256 in the table above is
unchanged, which is the check that proves it.

Superseded archive, **do not use**: `RICE_curated_phase2.zip`, 931,860,119 bytes,
sha256 `2161e0691c5fef43a37274a7331adee7b6267b5032547a7320554804a19fa3ab`.

## Counts

| Split | Images | Boxes | rice_protect | weed_target | Groups (re-derived) | EXIF-normalized |
|---|---:|---:|---:|---:|---:|---:|
| train | 1,800 | 59,691 | 52,194 | 7,497 | 83 | 35 |
| valid | 518 | 15,226 | 13,201 | 2,025 | 34 | 80 |
| test (see limitations) | 261 | 6,284 | 5,355 | 929 | 25 | 99 |
| **total** | **2,579** | **81,201** | **70,750** | **10,451** | — | **214** |

Reconciled against the manifest's own `per_split` totals (81,204 source boxes):
train loses exactly the 3 annotations the sanitation rule rejected (2 rice, 1
weed); valid and test lose none. Class balance is roughly **6.96 : 1** rice to
weed in train.

## What the build does to the source

1. **Assignment by manifest, not by folder.** The source is laid out in native
   Roboflow `train/valid/test` folders that disagree with `grouped_split.json` for
   940 of 2,316 files. Every image is placed by the manifest.
2. **EXIF orientation applied and stripped.** 214 of 2,579 source images carry
   orientation tag 8 — stored landscape, annotated portrait (e.g. raw 3648×2048,
   COCO record 2048×3648). Their boxes were effectively transposed relative to
   their pixels. `ImageOps.exif_transpose` is applied, the EXIF block removed, and
   the result re-encoded (JPEG q=95). **Only those 214 are re-encoded**; the other
   2,365 are byte-identical to source. The build fails if any normalized image
   still disagrees with its COCO dimensions.
3. **One box rule, applied identically everywhere.** Clip an excursion of ≤1 px;
   reject anything further out, any non-positive or non-finite box, and anything
   under 1 px on a side after clipping. Result: **3 rejected** (all
   `out_of_bounds`), **115 clipped**, every case itemized in
   `reports/rejected_annotations.json`. The same rule must be used for evaluation
   ground truth.
4. **SAM polygons dropped.** The source `instances_*.coco.json` carry SAM2
   box-prompted polygons for all 81,204 boxes, but the source provenance marks
   them `review_status: unreviewed`, `human_edit_state: none`. This is a
   box-detection dataset; `--keep-segmentation` restores them if ever needed. Do
   not describe them as ground truth.
5. **Hashes and membership recorded.** Per-image sha256 in both the COCO
   `images[]` records and `manifests/split_membership.json`; sha256 for every
   emitted JSON in `manifests/provenance.json`.

## Verification

`agrinav data-build-rice-phase2 preflight --out-root <dir>` re-reads the tree from
disk and fails closed on: a missing image, a byte-level hash mismatch, decoded
dimensions disagreeing with the COCO record, a residual EXIF orientation tag, an
out-of-bounds or non-positive box, an unknown category, a file name or content
hash appearing in two splits, a file on disk that no COCO record claims, and any
disagreement with `grouped_split.json` (vendored into `manifests/` so the check
needs nothing from the build machine). Passed on 2026-07-29.

## Known limitations

**The `test` split is usable for a fresh model, not for the 2026-07-28
checkpoints.** `RICE_curated_phase2.zip` mis-exported 179 of these 261 images into
its train folder and two voided runs trained on it. But **no metric was ever
computed on them** — no evaluator existed until 2026-07-29 — so nothing was tuned
or reported against this split. Contamination is a property of the weights:
the 2026-07-28 checkpoints may never be scored on it; a model trained from
scratch on this build may use it normally. (Corrected 2026-07-29; this card first
said "burned", which was too strong.)

**A replacement test split is not buildable from the clean pool.** Measured, not
assumed. Of the 781 images with `trained_on_legacy: false`:

| Current split | Never trained on | Trained on |
|---|---:|---:|
| train | 539 | 1,261 |
| valid | 160 | 358 |
| test | 82 | 179 |
| **total** | **781** | **1,798** |

Those 781 span 89 re-derived groups — but **83 of those groups also contain a
trained-on image**, leaving only **6** images in a fully clean group, and those 6
carry **zero weed boxes**. A group-respecting split drawn from the clean pool is
empty in practice; selecting at the image level instead would reintroduce the
adjacent-frame leakage grouping exists to prevent. The clean pool's class balance
matches the whole dataset (6.78:1 rice-to-weed, 51.0% of images weed-bearing
versus 51.3% overall), so it is representative — it is simply not separable.

**Group ids are re-derived, not original.** `grouped_split.json` records
`num_groups: 68` and `block_size: 40` but no per-file group ids, so
`derive_group_id()` reconstructs the *shape* of the key (capture-family stem +
`frame // 40`) and yields 142 groups across the three splits. It is a diagnostic,
not the provenance of the existing assignment.

**Residual block-boundary leakage in the intended split.** 3 re-derived groups
straddle a split boundary, because 40-frame blocks cut video sequences and
adjacent frames are near-duplicates. Zero exact-hash duplicates anywhere.

**Small objects dominate.** Measured after letterbox to 512 px: 56.0% of train
boxes are COCO-small, 32.6% have a minimum side under 16 px, median box is
20.8 × 41.7 px, median image holds 31 annotated objects. 512 px should not be
accepted as the input resolution without a resolution / tiled-inference study.

**Category naming in the source is inconsistent.** The per-split
`images/<split>/_annotations.coco.json` files in the *source* use Roboflow's raw
names (`rice`, `weed`) plus a junk id-0 supercategory, while
`annotations/instances_*.coco.json` use `rice_protect` / `weed_target`. Boxes are
identical. The rebuild emits only the latter. The trainer's dataset accepts a
*partial* class-name match, so pointing `--ann-file` at the wrong file with the
wrong `--class-names` could silently train fewer classes than intended.

**Provenance and licensing.** The Roboflow RICE export's licence is **not
recorded** anywhere in this repository, and no project-wide code licence has been
selected. Resolve both before any public release or redistribution. The SAM2
proposal model revision is recorded as `UNPINNED_UPSTREAM` in the source
provenance — pin it before any release use of the polygons.

**Domain coverage is unmeasured.** The manifest carries no farm, season, device,
camera-height, or illumination metadata, so nothing here supports a claim about
generalization beyond this capture population. A same-dataset AP is not a
field-readiness claim.

## Regenerate

```bash
agrinav data-build-rice-phase2 build \
  --source-root <deliverable>/detection/RICE \
  --out-root <dir> \
  --legacy-archive <path to RICE_curated_phase2.zip>

agrinav data-build-rice-phase2 preflight --out-root <dir>

agrinav data-build-rice-phase2 package --out-root <dir> --zip RICE_phase2_rebuild.zip
```

`package` excludes the test split by default, so the uploaded training archive
cannot contain it. `--legacy-archive` is optional and only supplies the
`trained_on_legacy` flags.
