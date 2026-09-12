"""FastAPI app exposing the RAG model layer.

Endpoints
---------
* ``GET  /health``   liveness — always cheap, never loads models.
* ``GET  /ready``    readiness — reports which backends are loaded/configured.
* ``POST /embed``    dense embeddings via BGE-M3.
* ``POST /rerank``   cross-encoder reranking via bge-reranker-v2-m3.
* ``POST /generate`` LLM generation proxied to an Ollama service.

Models are loaded lazily (see ``config.preload_models``) so the container
reports healthy to Cloud Run before the heavy model weights finish loading.
Heavy ML imports live inside the loader functions so the module imports fast
and ``/health`` works even if the ML stack is misconfigured.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

LLMRole = Literal["utility", "generation"]

from rag_service.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("rag_service")

app = FastAPI(
    title="EagleGIS RAG model service",
    description=(
        "Standalone model-serving layer for EagleGIS Retrieval-Augmented "
        "Generation: embeddings (BGE-M3), reranking (bge-reranker-v2-m3), and "
        "LLM generation proxied to Ollama."
    ),
    version=settings.service_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    logger.info("loading embedding model %s on %s", settings.embedding_model, settings.device)
    return SentenceTransformer(settings.embedding_model, device=settings.device)


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder

    logger.info("loading reranker model %s on %s", settings.reranker_model, settings.device)
    return CrossEncoder(settings.reranker_model, device=settings.device)


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="Texts to embed")
    normalize: bool = Field(True, description="L2-normalize vectors (recommended for cosine)")


class EmbedResponse(BaseModel):
    model: str
    dim: int
    embeddings: list[list[float]]


@app.post("/embed", response_model=EmbedResponse, tags=["Models"])
def embed(req: EmbedRequest) -> EmbedResponse:
    model = _embedder()
    vecs = model.encode(
        req.texts,
        normalize_embeddings=req.normalize,
        convert_to_numpy=True,
    )
    return EmbedResponse(
        model=settings.embedding_model,
        dim=int(vecs.shape[1]),
        embeddings=vecs.tolist(),
    )


# --------------------------------------------------------------------------- #
# Reranking
# --------------------------------------------------------------------------- #
class RerankRequest(BaseModel):
    query: str
    documents: list[str] = Field(..., min_length=1)
    top_k: Optional[int] = Field(None, ge=1, description="Return only the top-k after reranking")


class RerankItem(BaseModel):
    index: int
    score: float
    document: str


class RerankResponse(BaseModel):
    model: str
    results: list[RerankItem]


@app.post("/rerank", response_model=RerankResponse, tags=["Models"])
def rerank(req: RerankRequest) -> RerankResponse:
    model = _reranker()
    pairs = [(req.query, doc) for doc in req.documents]
    scores = model.predict(pairs)
    ranked = sorted(
        (
            RerankItem(index=i, score=float(score), document=doc)
            for i, (score, doc) in enumerate(zip(scores, req.documents))
        ),
        key=lambda item: item.score,
        reverse=True,
    )
    if req.top_k is not None:
        ranked = ranked[: req.top_k]
    return RerankResponse(model=settings.reranker_model, results=ranked)


# --------------------------------------------------------------------------- #
# Generation (proxied to role-tiered Ollama services)
# --------------------------------------------------------------------------- #
def _build_payload(prompt: str, model: str, *, system: Optional[str], temperature: float, fmt: Any) -> dict:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system
    if fmt is not None:
        payload["format"] = fmt
    return payload


def _resolve_role(role: LLMRole) -> tuple[str, str]:
    base_url, default_model = settings.llm(role)
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail=(
                f"No Ollama URL configured for role '{role}'. Set "
                f"{'GENERATION_OLLAMA_URL' if role == 'generation' else 'UTILITY_OLLAMA_URL'} "
                "(or OLLAMA_BASE_URL as a fallback)."
            ),
        )
    return base_url, default_model


async def _ollama_generate(client: httpx.AsyncClient, base_url: str, payload: dict) -> str:
    resp = await client.post(base_url.rstrip("/") + "/api/generate", json=payload)
    resp.raise_for_status()
    return resp.json().get("response", "")


class GenerateRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    role: LLMRole = Field("generation", description="Which model tier to use")
    model: Optional[str] = Field(None, description="Override the role's default model")
    temperature: float = 0.2
    # Pass an Ollama-compatible JSON schema to force structured output.
    format: Optional[Any] = Field(None, description="Ollama 'format' (e.g. 'json' or a JSON schema)")


class GenerateResponse(BaseModel):
    model: str
    role: LLMRole
    response: str


@app.post("/generate", response_model=GenerateResponse, tags=["Models"])
async def generate(req: GenerateRequest) -> GenerateResponse:
    base_url, default_model = _resolve_role(req.role)
    model = req.model or default_model
    payload = _build_payload(
        req.prompt, model, system=req.system, temperature=req.temperature, fmt=req.format
    )
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            text = await _ollama_generate(client, base_url, payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {exc}") from exc
    return GenerateResponse(model=model, role=req.role, response=text)


class BatchGenerateRequest(BaseModel):
    prompts: list[str] = Field(..., min_length=1, description="Prompts to run concurrently")
    system: Optional[str] = None
    role: LLMRole = Field("utility", description="Defaults to the small high-concurrency tier")
    model: Optional[str] = None
    temperature: float = 0.2
    format: Optional[Any] = None
    max_concurrency: Optional[int] = Field(None, ge=1, description="Cap on in-flight calls")


class BatchGenerateResponse(BaseModel):
    model: str
    role: LLMRole
    responses: list[str]
    errors: list[Optional[str]]


@app.post("/generate_batch", response_model=BatchGenerateResponse, tags=["Models"])
async def generate_batch(req: BatchGenerateRequest) -> BatchGenerateResponse:
    """Fan a list of prompts out to a model tier concurrently.

    This is the primitive the agentic loop uses for concurrent work — e.g.
    CRAG grading one prompt per retrieved document, or contextualizing many
    chunks at ingest — bounded by a semaphore so a wide fan-out can't overwhelm
    the downstream service.
    """
    base_url, default_model = _resolve_role(req.role)
    model = req.model or default_model
    limit = req.max_concurrency or settings.max_concurrency
    sem = asyncio.Semaphore(limit)

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        async def run_one(prompt: str) -> tuple[str, Optional[str]]:
            payload = _build_payload(
                prompt, model, system=req.system, temperature=req.temperature, fmt=req.format
            )
            async with sem:
                try:
                    return await _ollama_generate(client, base_url, payload), None
                except httpx.HTTPError as exc:
                    return "", f"{type(exc).__name__}: {exc}"

        results = await asyncio.gather(*(run_one(p) for p in req.prompts))

    return BatchGenerateResponse(
        model=model,
        role=req.role,
        responses=[r for r, _ in results],
        errors=[e for _, e in results],
    )


# --------------------------------------------------------------------------- #
# Health / readiness
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "service": settings.service_name, "version": settings.service_version}


@app.get("/ready", tags=["System"])
def ready() -> dict:
    return {
        "embedder_loaded": _embedder.cache_info().currsize > 0,
        "reranker_loaded": _reranker.cache_info().currsize > 0,
        "generation_llm_configured": bool(settings.generation_ollama_url),
        "utility_llm_configured": bool(settings.utility_ollama_url),
        "device": settings.device,
    }


@app.on_event("startup")
def _maybe_preload() -> None:
    if settings.preload_models:
        logger.info("PRELOAD_MODELS=true — loading models at startup")
        _embedder()
        _reranker()
