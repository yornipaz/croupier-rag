from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from app.modules.vector_store.application.dto.embedded import EmbeddedChunk
from app.modules.vector_store.application.dto.search import SearchHit, SparseVector
from app.modules.vector_store.application.ports.vector_store import VectorStorePort
from app.shared.chunks import Chunk
from app.shared.resilience.circuit_breaker import CircuitBreaker
from app.shared.resilience.policy import resilient


class ResilientVectorStore:
    """Same ``VectorStorePort`` contract, wrapped with timeout + retry + breaker."""

    def __init__(
        self,
        inner: VectorStorePort,
        *,
        name: str,
        timeout_s: float,
        max_retries: int,
        base_delay_s: float,
        max_delay_s: float,
        breaker: CircuitBreaker | None = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._breaker = breaker or CircuitBreaker(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._ensure_collection: Callable[[], Awaitable[None]] = resilient(
            name=f"{name}:ensure",
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.ensure_collection)
        self._upsert: Callable[[Sequence[Chunk]], Awaitable[None]] = resilient(
            name=f"{name}:upsert",
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.upsert)
        self._upsert_embedded: Callable[[Sequence[EmbeddedChunk]], Awaitable[None]] = resilient(
            name=f"{name}:upsert-embedded",
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.upsert_embedded)
        self._search: Callable[
            [Sequence[float], SparseVector, int, str | None],
            Awaitable[list[SearchHit]],
        ] = resilient(
            name=f"{name}:search",
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.hybrid_search)
        self._delete: Callable[[str], Awaitable[None]] = resilient(
            name=f"{name}:delete",
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.delete_by_doc)

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def ensure_collection(self) -> None:
        await self._ensure_collection()

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        await self._upsert(chunks)

    async def upsert_embedded(self, chunks: Sequence[EmbeddedChunk]) -> None:
        await self._upsert_embedded(chunks)

    async def hybrid_search(
        self,
        dense: Sequence[float],
        sparse: SparseVector,
        top_k: int,
        doc_id: str | None = None,
    ) -> list[SearchHit]:
        return await self._search(dense, sparse, top_k, doc_id)

    async def delete_by_doc(self, doc_id: str) -> None:
        await self._delete(doc_id)
