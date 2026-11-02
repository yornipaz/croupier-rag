from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.modules.vector_store.application.dto.embedded import EmbeddedChunk
from app.modules.vector_store.application.dto.search import SearchHit, SparseVector
from app.shared.chunks import Chunk


class VectorStorePort(Protocol):
    """Hybrid vector store contract. Payloads always carry the full Chunk."""

    async def ensure_collection(self) -> None: ...

    async def upsert(self, chunks: Sequence[Chunk]) -> None: ...

    async def upsert_embedded(self, chunks: Sequence[EmbeddedChunk]) -> None: ...

    async def hybrid_search(
        self,
        dense: Sequence[float],
        sparse: SparseVector,
        top_k: int,
        doc_id: str | None = None,
    ) -> list[SearchHit]: ...

    async def delete_by_doc(self, doc_id: str) -> None: ...
