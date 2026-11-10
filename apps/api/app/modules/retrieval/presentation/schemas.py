from __future__ import annotations

from pydantic import Field

from app.modules.retrieval.application.dto.retrieval import (
    RetrievalDebug,
    RetrievalResult,
    RetrievedChunk,
    RetrievedImage,
)
from app.shared.chunks import BBox
from app.shared.schemas import CamelModel


class RetrievalRequest(CamelModel):
    query: str = Field(min_length=1)
    doc_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=100)


class RetrievedChunkSchema(CamelModel):
    id: str
    doc_id: str
    page: int
    bbox: BBox
    section_path: list[str]
    kind: str
    text: str
    image_ids: list[str]
    token_count: int
    score: float
    relevance_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    dense_cosine: float | None = None

    @classmethod
    def from_dto(cls, item: RetrievedChunk) -> RetrievedChunkSchema:
        chunk = item.chunk
        return cls(
            id=chunk.id,
            doc_id=chunk.doc_id,
            page=chunk.page,
            bbox=chunk.bbox,
            section_path=list(chunk.section_path),
            kind=chunk.kind,
            text=chunk.text,
            image_ids=list(chunk.image_ids),
            token_count=chunk.token_count,
            score=item.score,
            relevance_score=item.relevance_score,
            dense_rank=item.dense_rank,
            sparse_rank=item.sparse_rank,
            dense_score=item.dense_score,
            sparse_score=item.sparse_score,
            dense_cosine=item.dense_cosine,
        )


class RetrievedImageSchema(CamelModel):
    url: str
    page: int
    bbox: BBox
    image_id: str
    doc_id: str
    score: float
    distance_pt: float
    source_indexes: list[int]

    @classmethod
    def from_dto(cls, item: RetrievedImage) -> RetrievedImageSchema:
        return cls(
            url=item.url,
            page=item.page,
            bbox=item.bbox,
            image_id=item.image_id,
            doc_id=item.document_id,
            score=item.score,
            distance_pt=item.distance_pt,
            source_indexes=list(item.source_indexes),
        )


class RetrievalDebugHitSchema(CamelModel):
    chunk_id: str
    doc_id: str
    page: int
    section_path: list[str]
    kind: str
    fused_score: float
    dense_cosine: float | None = None
    sent: bool
    rrf_score: float
    relevance_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None


class RetrievalDebugSchema(CamelModel):
    retrieved: list[RetrievalDebugHitSchema]
    lexical_coverage: float

    @classmethod
    def from_dto(cls, debug: RetrievalDebug) -> RetrievalDebugSchema:
        return cls(
            retrieved=[
                RetrievalDebugHitSchema(
                    chunk_id=item.chunk_id,
                    doc_id=item.doc_id,
                    page=item.page,
                    section_path=list(item.section_path),
                    kind=item.kind,
                    fused_score=item.rrf_score,
                    dense_cosine=item.dense_cosine,
                    sent=item.sent,
                    rrf_score=item.rrf_score,
                    relevance_score=item.relevance_score,
                    dense_rank=item.dense_rank,
                    sparse_rank=item.sparse_rank,
                    dense_score=item.dense_score,
                    sparse_score=item.sparse_score,
                )
                for item in debug.retrieved
            ],
            lexical_coverage=debug.lexical_coverage,
        )


class RetrievalResponse(CamelModel):
    chunks: list[RetrievedChunkSchema]
    images: list[RetrievedImageSchema]
    top_score: float
    debug: RetrievalDebugSchema | None = None

    @classmethod
    def from_result(
        cls,
        result: RetrievalResult,
        *,
        include_debug: bool,
    ) -> RetrievalResponse:
        return cls(
            chunks=[RetrievedChunkSchema.from_dto(item) for item in result.chunks],
            images=[RetrievedImageSchema.from_dto(item) for item in result.images],
            top_score=result.top_score,
            debug=RetrievalDebugSchema.from_dto(result.debug) if include_debug else None,
        )
