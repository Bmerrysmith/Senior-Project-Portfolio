# Detector training quickstart

Agrinav trains the WeedDet detector against COCO-format annotations. Keep the
test split sealed during iteration; provide the training split and, when
available, the validation split for checkpoint selection.

```bash
python -m agrinav.training.weeddet_train --ann-file data/splits/train.coco.json --images-root data/images --val-ann-file data/splits/val.coco.json --val-images-root data/images --config configs/weeddet_v6b.yaml --checkpoint-dir checkpoints/weeddet
```

The repository intentionally does not include the source images, private
datasets, or trained weights. Replace the example paths with local copies of
your COCO annotations and image root. For a no-data wiring check, use
`python -m agrinav.training.weeddet_train --self-test`.

The training entry point records configuration, metrics, checkpoints, and
gradient diagnostics. See [Portfolio results](PORTFOLIO_RESULTS.md) for the
measured outcomes included in this public snapshot.
