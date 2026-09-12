# syntax=docker/dockerfile:1
#
# Container image for the EagleGIS RAG model service.
# Build context is this directory (rag_service/), keeping the image lean.
#
#   docker build -t eaglegis-rag rag_service
#   docker run --rm -p 8080:8080 eaglegis-rag
#
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Hugging Face cache; writable by the non-root user below.
    HF_HOME=/models \
    PORT=8080

WORKDIR /app

# curl is only used by the optional HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Non-root user (Cloud Run best practice) + writable model cache dir.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /models \
    && chown -R appuser:appuser /app /models

# Copy the service package so it imports as `rag_service.main`.
COPY --chown=appuser:appuser . ./rag_service/

USER appuser

# Optionally bake the model weights into the image to avoid a cold-start
# download. This makes the image multi-GB, so it's opt-in:
#   docker build --build-arg PRELOAD_MODELS=true -t eaglegis-rag rag_service
ARG PRELOAD_MODELS=false
ARG EMBEDDING_MODEL=BAAI/bge-m3
ARG RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RUN if [ "$PRELOAD_MODELS" = "true" ]; then \
        python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('${EMBEDDING_MODEL}'); CrossEncoder('${RERANKER_MODEL}')"; \
    fi

EXPOSE 8080

# Cloud Run ignores Docker HEALTHCHECK, but it's useful for local/compose runs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8080}/health" || exit 1

# Shell form so ${PORT} (injected by Cloud Run) is expanded at runtime.
CMD exec uvicorn rag_service.main:app --host 0.0.0.0 --port ${PORT:-8080}
