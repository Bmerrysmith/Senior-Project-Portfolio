# License Plate Detection

A UK license plate recognition pipeline that combines YOLOv8 vehicle detection, classical image processing for plate localization, and a three-engine OCR ensemble — including a locally-hosted vision-language model — with plate-specific error correction.

## Pipeline

1. **Vehicle detection** — YOLOv8n locates the car in frame and crops to that region, falling back to a fixed crop band if no vehicle is detected.
2. **Plate localization** — a LAB-colorspace brightness-peak search finds the plate's column and row extent within the vehicle crop (no plate-specific model needed for this step).
3. **Plate preparation** — Lanczos super-resolution, rotation correction, and a set of CLAHE/sharpen/denoise variants are generated from the crop to give each OCR engine its best shot.
4. **OCR ensemble** — three independent readers vote on the plate text:
   - **Ollama vision** (`llava:7b` by default) reads the plate directly from the image, sampled multiple times with character-level consensus voting across runs.
   - **EasyOCR** reads each processed variant with a character allowlist.
   - **fast-plate-ocr** runs a dedicated plate-recognition model as a third opinion.
5. **UK plate correction** — results are validated against the UK new-style format (2 letters, 2 digits, 3 letters) and corrected for OCR-common character confusions (e.g. `O`/`0`, `I`/`1`, `S`/`5`) using position-aware substitution tables, then checked against a blocklist of known false-positive reads.

## Running it

```bash
pip install -r requirements.txt
```

You'll also need a running [Ollama](https://ollama.com) instance with a vision model pulled (`ollama pull llava:7b`), pointed to by the `OLLAMA_BASE` env var (defaults to `http://localhost:11434`).

```bash
export IMG_PATH=licenseImage.jpg      # image to process
export OLLAMA_BASE=http://localhost:11434
export OLLAMA_MODEL=llava:7b
python pipeline_final.py
```

Intermediate images from every pipeline stage (ROI crop, plate crop, prepared variants) are written to `debug_outputs/` for inspection.

## Notes

- Correction logic and the plate format check are UK-specific; adapting to other plate formats means swapping `is_valid_uk_plate` / `correct_uk`.
- `fast-plate-ocr` and `easyocr` both fall back gracefully if unavailable — the pipeline still runs on Ollama vision alone.
