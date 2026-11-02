from __future__ import annotations

from dataclasses import dataclass

from app.shared.chunks import Chunk


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Sparse lexical representation exchanged with the vector store."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One fused hit plus the component ranks/scores used by debug mode."""

    chunk: Chunk
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
