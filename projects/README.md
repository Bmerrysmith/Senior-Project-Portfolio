# Project Source

Curated source from three of my projects. These are excerpts, not full mirrors —
large data/result files, virtual environments, and model weight files are left out
to keep the repo light.

For full history and complete trees, see the original repos:

- **QuakeTwin** — https://github.com/ishitachakka/QuakeTwin
- **License Plate Detection** — https://github.com/ishitachakka/licensePlateDetection
- **SimilarityAPI** — https://github.com/ishitachakka/SimilarityAPI

## quaketwin/

QKD-secured digital twin for post-disaster transportation infrastructure. What's here:

- `api/` — FastAPI backend (digital twin state, pavement condition, websocket streaming, Azure Digital Twins client, Cesium integration)
- `ai/` — the QKD/SeQUeNCe quantum network simulation and the experiment results it produced
- `models/` — JSON schemas for the digital twin entities (roads, pavement assets, traffic sensors)
- `figures/` — result plots from the experiment suite

## licenseplatedetection/

YOLOv8 + multi-engine OCR pipeline for UK license plate recognition. `pipeline_final.py` is the whole pipeline: vehicle detection, plate localization, image preparation, and the three-way OCR ensemble with UK-plate correction logic.

## similarityapi/

FastAPI semantic similarity service. `main.py` is the full service — OpenAI embeddings, Qdrant retrieval, and a Word2Vec-based cosine similarity fallback path.
