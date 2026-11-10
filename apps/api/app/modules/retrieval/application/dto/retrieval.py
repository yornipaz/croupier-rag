from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace

from app.shared.chunks import BBox, Chunk, ChunkKind


@dataclass(frozen=True, slots=True)
class ImageAsset:
    document_id: str
    image_id: str
    page: int
    bbox: BBox


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    relevance_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    dense_cosine: float | None = None
    sparse_indices: tuple[int, ...] | None = None
    dense_vector: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class RetrievedImage:
    document_id: str
    image_id: str
    page: int
    bbox: BBox
    url: str
    score: float
    distance_pt: float
    source_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RetrievalDebugHit:
    chunk_id: str
    doc_id: str
    page: int
    section_path: tuple[str, ...]
    kind: ChunkKind
    rrf_score: float
    relevance_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    dense_cosine: float | None = None
    sent: bool = False


@dataclass(frozen=True, slots=True)
class SelectionDrop:
    chunk_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class SelectionDebug:
    mode: str
    enabled: bool
    decision: str
    signals: dict[str, float]
    thresholds: dict[str, float]
    kept: tuple[str, ...]
    dropped: tuple[SelectionDrop, ...]


@dataclass(frozen=True, slots=True)
class RetrievalDebug:
    retrieved: tuple[RetrievalDebugHit, ...]
    lexical_coverage: float = 0.0
    selection: SelectionDebug | None = None

    def with_sent(self, chunk_ids: Collection[str]) -> RetrievalDebug:
        """Return a copy marking which candidate chunks were sent to the LLM."""
        sent_ids = set(chunk_ids)
        return RetrievalDebug(
            retrieved=tuple(replace(hit, sent=hit.chunk_id in sent_ids) for hit in self.retrieved),
            lexical_coverage=self.lexical_coverage,
            selection=self.selection,
        )


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunks: tuple[RetrievedChunk, ...]
    images: tuple[RetrievedImage, ...]
    top_score: float
    debug: RetrievalDebug
