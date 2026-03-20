"""Embedding provider abstraction — local BGE-M3 or cloud Dashscope.

Usage:
    from domain.knowledge.embedding import embed, embed_batch, preload_embedding_model
    preload_embedding_model()  # call at app startup
    vec = embed("头痛2周伴恶心呕吐")  # → list of 1024 floats
"""
from __future__ import annotations

import os
from typing import List, Optional

from utils.log import log

_model = None
_provider: Optional[str] = None


def _get_provider() -> str:
    return os.environ.get("EMBEDDING_PROVIDER", "local")


def _get_model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")


def preload_embedding_model() -> None:
    """Load embedding model at startup. Call once during app lifespan."""
    global _model, _provider
    _provider = _get_provider()

    if _provider == "local":
        try:
            from sentence_transformers import SentenceTransformer
            model_name = _get_model_name()
            log(f"[embedding] loading local model: {model_name}")
            _model = SentenceTransformer(model_name)
            log(f"[embedding] model loaded: {model_name}")
        except Exception as e:
            log(f"[embedding] failed to load model: {e}", level="warning")
            _model = None
    elif _provider == "dashscope":
        log("[embedding] dashscope provider — no preload needed")
    else:
        log(f"[embedding] unknown provider: {_provider}", level="warning")


def embed(text: str) -> List[float]:
    """Embed a single text string. Returns list of floats (1024-d for BGE-M3)."""
    provider = _provider or _get_provider()

    if provider == "local":
        if _model is None:
            raise RuntimeError("Embedding model not loaded. Call preload_embedding_model() first.")
        vec = _model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    elif provider == "dashscope":
        import dashscope
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=text,
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        )
        return resp.output["embeddings"][0]["embedding"]

    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts. Returns list of embedding vectors."""
    provider = _provider or _get_provider()

    if provider == "local":
        if _model is None:
            raise RuntimeError("Embedding model not loaded. Call preload_embedding_model() first.")
        vecs = _model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    elif provider == "dashscope":
        import dashscope
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=texts,
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        )
        return [e["embedding"] for e in resp.output["embeddings"]]

    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def get_model_name() -> str:
    """Return the current embedding model name for storage tracking."""
    provider = _provider or _get_provider()
    if provider == "local":
        return _get_model_name()
    elif provider == "dashscope":
        return "dashscope/text-embedding-v3"
    return f"unknown/{provider}"
