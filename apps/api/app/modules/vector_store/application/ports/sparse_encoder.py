from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.modules.vector_store.application.dto.search import SparseVector


class SparseEncoderPort(Protocol):
    """Sparse lexical encoder (BM25) used for hybrid retrieval."""

    async def embed(self, texts: Sequence[str]) -> list[SparseVector]: ...
