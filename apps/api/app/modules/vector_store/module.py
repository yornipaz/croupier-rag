from __future__ import annotations

from fastapi import APIRouter
from qdrant_client import AsyncQdrantClient

from app.config.settings import Settings
from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.vector_store.application.ports.sparse_encoder import SparseEncoderPort
from app.modules.vector_store.application.ports.vector_store import VectorStorePort
from app.modules.vector_store.infrastructure.fastembed_bm25 import FastEmbedBM25
from app.modules.vector_store.infrastructure.qdrant import QdrantVectorStore
from app.modules.vector_store.infrastructure.resilient import ResilientVectorStore
from app.modules.vector_store.presentation.router import router
from app.shared.resilience.circuit_breaker import CircuitBreaker

__all__ = [
    "SparseEncoderPort",
    "VectorStorePort",
    "build_sparse_encoder",
    "build_vector_store",
    "build_vector_store_module",
    "build_vector_store_router",
    "router",
]


def build_sparse_encoder(settings: Settings) -> SparseEncoderPort:
    """Build the Spanish BM25 sparse encoder used by hybrid retrieval."""
    return FastEmbedBM25(
        model_name=settings.sparse_embedding_model,
        language=settings.sparse_embedding_language,
    )


def build_vector_store(
    settings: Settings,
    *,
    client: AsyncQdrantClient,
    embedding: EmbeddingPort,
    sparse_encoder: SparseEncoderPort,
    breaker: CircuitBreaker | None = None,
    resilient: bool = True,
) -> VectorStorePort:
    """Compose the Qdrant adapter (and its resilience wrapper) as a port."""
    store: VectorStorePort = QdrantVectorStore(
        client,
        collection_name=settings.qdrant_collection,
        embedding=embedding,
        sparse_encoder=sparse_encoder,
        prefetch_limit=settings.retrieval_prefetch_limit,
    )
    if not resilient:
        return store
    return ResilientVectorStore(
        store,
        name=f"vector-store:qdrant:{settings.qdrant_collection}",
        timeout_s=settings.vector_store_timeout_s,
        max_retries=settings.http_max_retries,
        base_delay_s=settings.http_retry_base_s,
        max_delay_s=settings.http_retry_max_s,
        breaker=breaker,
        failure_threshold=settings.breaker_failure_threshold,
        recovery_timeout=settings.breaker_recovery_s,
    )


def build_vector_store_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_vector_store_module(settings: Settings) -> APIRouter:
    return build_vector_store_router(settings)
