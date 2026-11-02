from __future__ import annotations

from dataclasses import dataclass

from app.modules.vector_store.application.dto.search import SparseVector
from app.shared.chunks import Chunk


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """A chunk plus the vectors produced by the ingestion embedding stage."""

    chunk: Chunk
    dense: tuple[float, ...]
    sparse: SparseVector
