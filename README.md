# Ishita Chakkalakkal

Software Engineering, Florida Gulf Coast University | Expected May 2027
Focus: LLM agent systems, RAG pipelines, and quantum ML applied to infrastructure resilience

[GitHub](https://github.com/ishitachakka) · [LinkedIn](https://www.linkedin.com/in/ishitachakkalakkal-494113243)

---

## QuakeTwin — QKD-Secured Digital Twin for Post-Disaster Infrastructure

**Role:** Research Assistant, FGCU EagleCyberNest Lab
**Links:** [Live platform](https://quake-twin.vercel.app) · [Backend API](https://quaketwin-production.up.railway.app) · [Repo](https://github.com/ishitachakka/QuakeTwin)

### What it is

Most digital twin systems for transportation assume communication just works. After a hurricane, it doesn't — cellular towers go down, fiber links get cut, and the sensor data emergency responders depend on arrives late or not at all, while physically damaged infrastructure becomes accessible to adversaries who can spoof readings. QuakeTwin is a digital twin platform built around that reality: it couples a QKD-secured V2X communication layer with SeQUeNCe-based quantum network simulation to model what happens to infrastructure recovery decisions when communication degrades and comes under attack. The platform runs on real FDOT pavement data, Google Street View imagery, and Florida DOT traffic feeds. Co-authored paper accepted at IEEE VTC2026-Fall Boston; currently extending the system with drone integration and multi-agent coordination.

### What I built

- **QKD-secured communication layer.** BB84/CV-QKD channels simulated via SeQUeNCe, with configurable latency and packet-loss models standing in for real disaster-degraded links.
- **Security fallback logic.** QBER is monitored continuously — when it crosses the 11% Shor-Preskill threshold, the channel is flagged as compromised and the system falls back to cached digital-twin state rather than acting on data that may have been spoofed.
- **Reward function design & RL pipelines.** Designed reward functions and RL agent pipelines integrated with Unity–Cesium simulation environments for real-time infrastructure visualization and decision-making.
- **FastAPI backend** serving the digital twin state and experiment results, deployed on Railway.
- **Experiment suite.** Six experiments across ten independent seeds — latency sweep, MITM attack security, lambda sensitivity, combined stress, packet-loss degradation, and SeQUeNCe channel sensitivity — with results published alongside the code.
- **Real-world data integration.** FDOT pavement condition data, Google Street View imagery, and Florida DOT traffic feeds feed the physical layer instead of synthetic inputs.

### Selected outcomes

| Outcome | Measured result |
|---|---:|
| Decision accuracy under disaster conditions (40% packet loss) | QKD-secured: **82.7%** vs. unprotected PPO: **67.5%** — a 15.2 point gap |
| Accuracy holds under active attack | Near-perfect up to **20% MITM attack rate**; unprotected channels degrade immediately past 10% |

### Stack

Python, FastAPI, SeQUeNCe (quantum network simulation), Unity, Cesium, Vercel, Railway

### What I took away

The interesting failure mode wasn't the quantum layer, it was deciding what to do when you can't trust it: proving the channel is compromised is only useful if the system has a safe fallback, so half the engineering here is a well-defined "act on stale-but-honest state" path rather than a smarter attack detector.

---

## License Plate Detection

**Links:** [Repo](https://github.com/ishitachakka/licensePlateDetection)

### What it is

A UK license plate recognition pipeline combining YOLOv8 vehicle detection, classical image processing for plate localization, and a three-engine OCR ensemble — including a locally-hosted vision-language model — with plate-format-specific error correction.

### What I built

- **Vehicle + plate localization.** YOLOv8n crops to the vehicle, then a LAB-colorspace brightness-peak search finds the plate's bounding box within that crop without needing a plate-specific detector.
- **Multi-engine OCR ensemble.** A locally-hosted vision-language model (Ollama/LLaVA) reads the plate directly, sampled multiple times with character-level consensus voting; EasyOCR and a dedicated plate-recognition model (fast-plate-ocr) each vote independently across several image-processing variants (CLAHE, sharpen, denoise, super-resolution).
- **UK plate correction.** Results are validated against the UK new-style format and corrected for OCR-common character confusions (`O`/`0`, `I`/`1`, `S`/`5`, etc.) using position-aware substitution tables, then checked against a blocklist of known false-positive reads.

### Stack

Python, YOLOv8 (Ultralytics), OpenCV, Ollama (LLaVA), EasyOCR, fast-plate-ocr

### What I took away

No single OCR engine was reliable enough on its own — the accuracy came from ensembling three very different readers and using domain knowledge (the fixed UK plate format) to arbitrate between disagreeing votes, rather than from any one model being especially good.

---

## SimilarityAPI

**Links:** [Repo](https://github.com/ishitachakka/SimilarityAPI)

### What it is

A semantic similarity service for validating an answer against a knowledge base: given a candidate answer and either a direct comparison text or a Qdrant collection to check it against, it returns a similarity score and the supporting content it was compared to.

### What I built

- **Dual retrieval paths.** The same endpoint supports validating against a fixed reference text or, when none is given, retrieving the closest matching content from a live Qdrant vector store — both behind one API.
- **Embedding + scoring pipeline.** OpenAI embeddings locate candidate content in Qdrant; both texts are then tokenized and reduced to vectors via a Word2Vec model trained on the fly, and scored with cosine similarity.
- **Containerized deployment** with environment-based configuration for the OpenAI and Qdrant credentials.

### Stack

Python, FastAPI, OpenAI embeddings, Qdrant, gensim (Word2Vec), Docker

### What I took away

Building the fallback path (direct-text comparison, no vector DB required) turned out to matter as much as the Qdrant-backed path — it kept the service usable in contexts where a full knowledge base wasn't set up yet, and made testing far easier.

---

## Selected coursework and other work

- **Switch4Good Database System** — full-stack partnership-tracking system (Express, PostgreSQL, JWT auth) built with a team for a nonprofit community partner.
- **Automated Selenium/TestNG test suite** (CEN 4072, Software Testing) — built with Gabriella Vallar.
- **AI Platform Engineer, NetStratum Technologies — BlueMesh Platform** (Nov 2025–Present) — built and deployed Sally, a real-time voice AI companion for an elder-care calling service (Chatterbox TTS, Silero VAD, Distil-Whisper STT, multi-layer memory); fine-tuned GLM 4.5 Air (LoRA/QLoRA) for a production persona adapter served via vLLM; built voice-enabled AI agents and MCP connectors on the Oasis platform (proprietary; not included here).
- **Backend Developer Intern, CloudGen LLC — NextGen Platform** (Jun 2022–Nov 2025) — built and maintained FastAPI backend services, MCP server tools, and API routing infrastructure for LLM agent pipelines; designed vector database systems for AI chatbot and document retrieval across PostgreSQL, MySQL, and MongoDB (proprietary; not included here).

## Certifications

AWS Certified Cloud Practitioner (2025–2027) · NVIDIA Certified Associate — Generative AI & LLMs (2025–2027) · NVIDIA Certified Professional — Agentic AI (2026–2028)
