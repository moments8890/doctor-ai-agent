"""Embedding provider abstraction via LangChain — local BGE-M3 or cloud Dashscope.

Usage:
    from domain.knowledge.embedding import embed, embed_batch, preload_embedding_model
    preload_embedding_model()  # call at app startup
    vec = embed("头痛2周伴恶心呕吐")  # → list of 1024 floats

Powered by LangChain's Embeddings interface. Switching models is a config change:
    EMBEDDING_PROVIDER=local      → HuggingFaceEmbeddings (BGE-M3, default)
    EMBEDDING_PROVIDER=dashscope  → DashScopeEmbeddings (Alibaba Cloud)
    EMBEDDING_PROVIDER=openai     → OpenAIEmbeddings (if PHI allows)
"""
from __future__ import annotations

import os
from typing import List, Optional

from utils.log import log

_embeddings = None  # LangChain Embeddings instance
_provider: Optional[str] = None


def _get_provider() -> str:
    return os.environ.get("EMBEDDING_PROVIDER", "local")


def _get_model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")


def preload_embedding_model() -> None:
    """Load embedding model at startup. Call once during app lifespan."""
    global _embeddings, _provider
    _provider = _get_provider()

    if _provider == "local":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            model_name = _get_model_name()
            log(f"[embedding] loading local model via LangChain: {model_name}")
            _embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                encode_kwargs={"normalize_embeddings": True},
            )
            log(f"[embedding] model loaded: {model_name}")
        except Exception as e:
            log(f"[embedding] failed to load model: {e}", level="warning")
            _embeddings = None
    elif _provider == "dashscope":
        try:
            from langchain_community.embeddings import DashScopeEmbeddings
            _embeddings = DashScopeEmbeddings(
                model="text-embedding-v3",
                dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
            )
            log("[embedding] dashscope provider initialized via LangChain")
        except Exception as e:
            log(f"[embedding] dashscope init failed: {e}", level="warning")
            _embeddings = None
    else:
        log(f"[embedding] unknown provider: {_provider}", level="warning")


def embed(text: str) -> List[float]:
    """Embed a single text string. Returns list of floats (1024-d for BGE-M3)."""
    if _embeddings is None:
        raise RuntimeError("Embedding model not loaded. Call preload_embedding_model() first.")
    return _embeddings.embed_query(text)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts. Returns list of embedding vectors."""
    if _embeddings is None:
        raise RuntimeError("Embedding model not loaded. Call preload_embedding_model() first.")
    return _embeddings.embed_documents(texts)


def get_model_name() -> str:
    """Return the current embedding model name for storage tracking."""
    provider = _provider or _get_provider()
    if provider == "local":
        return _get_model_name()
    elif provider == "dashscope":
        return "dashscope/text-embedding-v3"
    return f"unknown/{provider}"
