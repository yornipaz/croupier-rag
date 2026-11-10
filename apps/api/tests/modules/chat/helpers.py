from __future__ import annotations

from app.modules.retrieval.application.dto.retrieval import (
    RetrievalDebug,
    RetrievalDebugHit,
    RetrievalResult,
    RetrievedChunk,
    RetrievedImage,
)
from app.shared.chunks import Chunk


def retrieval_result(top_score: float = 0.9) -> RetrievalResult:
    first = Chunk(
        id="chunk-1",
        doc_id="doc-1",
        page=1,
        bbox=(10.0, 10.0, 100.0, 20.0),
        section_path=("Manual",),
        kind="text",
        text="El modelo A-100 usa 220 V.",
        image_ids=("img-1",),
        token_count=8,
    )
    second = Chunk(
        id="chunk-2",
        doc_id="doc-2",
        page=2,
        bbox=(20.0, 200.0, 120.0, 220.0),
        section_path=("Guía",),
        kind="text",
        text="El modelo A-200 usa 380 V.",
        image_ids=("img-2",),
        token_count=8,
    )
    chunks = (
        RetrievedChunk(chunk=first, score=0.02, relevance_score=0.8),
        RetrievedChunk(chunk=second, score=0.03, relevance_score=top_score),
    )
    images = (
        RetrievedImage(
            document_id="doc-1",
            image_id="img-1",
            page=1,
            bbox=(10.0, 30.0, 100.0, 80.0),
            url="/documents/doc-1/pages/1/crop?bbox=10,30,100,80&highlight=false",
            score=0.8,
            distance_pt=10.0,
            source_indexes=(1,),
        ),
        RetrievedImage(
            document_id="doc-2",
            image_id="img-2",
            page=2,
            bbox=(20.0, 230.0, 120.0, 280.0),
            url="/documents/doc-2/pages/2/crop?bbox=20,230,120,280&highlight=false",
            score=top_score,
            distance_pt=10.0,
            source_indexes=(2,),
        ),
    )
    debug = RetrievalDebug(
        retrieved=(
            RetrievalDebugHit(
                chunk_id="chunk-1",
                doc_id="doc-1",
                page=1,
                section_path=("Manual",),
                kind="text",
                rrf_score=0.02,
                relevance_score=0.8,
                dense_cosine=0.8,
            ),
            RetrievalDebugHit(
                chunk_id="chunk-2",
                doc_id="doc-2",
                page=2,
                section_path=("Guía",),
                kind="text",
                rrf_score=0.03,
                relevance_score=top_score,
                dense_cosine=0.95,
            ),
        )
    )
    return RetrievalResult(
        chunks=chunks,
        images=images,
        top_score=top_score,
        debug=debug,
    )
