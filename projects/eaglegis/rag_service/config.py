"""Environment-driven settings for the RAG model service.

Everything is overridable via environment variables so the same image can run
locally, in CI, and on Cloud Run without code changes. Mirrors the style of
``app/config.py`` in the main application.
"""
from __future__ import annotations

import os


class Settings:
    service_name: str = os.getenv("SERVICE_NAME", "eaglegis-rag")
    service_version: str = "0.1.0"

    # --- Embedding + reranking (local sentence-transformers) ---
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    reranker_model: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    # "cpu" works everywhere; set to "cuda" when running on a GPU-enabled
    # Cloud Run service / machine.
    device: str = os.getenv("MODEL_DEVICE", "cpu")
    # When true, models load at startup (slower cold start, faster first
    # request). When false (default), models lazy-load on first use so the
    # container becomes healthy immediately.
    preload_models: bool = os.getenv("PRELOAD_MODELS", "false").lower() == "true"

    # --- Role-tiered LLMs (proxied to Ollama services) ---
    # The model layer is split so cheap/high-concurrency work and expensive
    # generation can run as separate, independently-scaled Cloud Run services:
    #   * "generation" -> larger model on GPU, low concurrency, final answers.
    #   * "utility"    -> small model on CPU, high concurrency, used for routing,
    #                     CRAG grading, query rewriting, HyDE, and ingest-time
    #                     contextualization (fanned out concurrently).
    # OLLAMA_BASE_URL / OLLAMA_MODEL remain as a single-service fallback so the
    # same image works whether you deploy one Ollama or two.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")

    generation_ollama_url: str = os.getenv("GENERATION_OLLAMA_URL", os.getenv("OLLAMA_BASE_URL", ""))
    generation_model: str = os.getenv("GENERATION_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:4b"))
    utility_ollama_url: str = os.getenv("UTILITY_OLLAMA_URL", os.getenv("OLLAMA_BASE_URL", ""))
    utility_model: str = os.getenv("UTILITY_MODEL", "qwen3:1.7b")

    # Default ceiling on concurrent in-flight calls when fanning out to a model
    # service (e.g. grading N docs at once). Keeps fan-out from overwhelming it.
    max_concurrency: int = int(os.getenv("RAG_MAX_CONCURRENCY", "8"))

    request_timeout: float = float(os.getenv("RAG_REQUEST_TIMEOUT", "120"))

    def llm(self, role: str) -> tuple[str, str]:
        """Return ``(base_url, model)`` for a logical LLM role.

        Falls back to the single-service ``OLLAMA_BASE_URL`` when a role-specific
        endpoint isn't configured.
        """
        if role == "generation":
            return self.generation_ollama_url, self.generation_model
        if role == "utility":
            return self.utility_ollama_url, self.utility_model
        raise ValueError(f"unknown LLM role: {role!r}")

    # Cloud Run injects PORT (defaults to 8080).
    port: int = int(os.getenv("PORT", "8080"))

    # CORS — tighten to the main app's origin in production.
    allowed_origins: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")


settings = Settings()
