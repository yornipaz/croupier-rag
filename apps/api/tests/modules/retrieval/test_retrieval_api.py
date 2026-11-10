from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.retrieval.application.dto.retrieval import (
    RetrievalDebug,
    RetrievalDebugHit,
    RetrievalResult,
    RetrievedChunk,
    RetrievedImage,
)
from app.modules.retrieval.presentation.router import (
    get_retrieve_context_use_case,
    router,
)
from app.shared.chunks import Chunk


class FakeRetrieve:
    async def execute(
        self,
        query: str,
        doc_id: str | None = None,
        top_k: int | None = None,
        *,
        selection_mode: str | None = None,
    ) -> RetrievalResult:
        _ = query, doc_id, top_k, selection_mode
        chunk = Chunk(
            id="chunk-1",
            doc_id="doc-1",
            page=2,
            bbox=(10.0, 20.0, 30.0, 40.0),
            section_path=("Manual",),
            kind="text",
            text="contenido",
            image_ids=("img-1",),
            token_count=2,
        )
        retrieved = RetrievedChunk(
            chunk=chunk,
            score=0.02,
            relevance_score=0.8,
            dense_rank=1,
            sparse_rank=2,
        )
        image = RetrievedImage(
            document_id="doc-1",
            image_id="img-1",
            page=2,
            bbox=(10.0, 50.0, 30.0, 80.0),
            url="/documents/doc-1/pages/2/crop?bbox=10,50,30,80&highlight=false",
            score=0.8,
            distance_pt=10.0,
            source_indexes=(1,),
        )
        debug = RetrievalDebug(
            retrieved=(
                RetrievalDebugHit(
                    chunk_id="chunk-1",
                    doc_id="doc-1",
                    page=2,
                    section_path=("Manual",),
                    kind="text",
                    rrf_score=0.02,
                    relevance_score=0.8,
                ),
            )
        )
        return RetrievalResult(
            chunks=(retrieved,),
            images=(image,),
            top_score=0.8,
            debug=debug,
        )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_retrieve_context_use_case] = lambda: FakeRetrieve()
    return app


def test_retrieval_api_hides_debug_by_default() -> None:
    with TestClient(_app()) as client:
        response = client.post("/retrieval/search", json={"query": "panel"})

    assert response.status_code == 200
    body = response.json()
    assert body["topScore"] == 0.8
    assert body["chunks"][0]["id"] == "chunk-1"
    assert body["images"][0]["imageId"] == "img-1"
    assert "debug" not in body


def test_retrieval_api_includes_debug_with_query_flag() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/retrieval/search?debug=true",
            json={"query": "panel", "topK": 3},
        )

    assert response.status_code == 200
    debug = response.json()["debug"]
    assert debug["retrieved"][0]["chunkId"] == "chunk-1"
    assert debug["retrieved"][0]["rrfScore"] == 0.02
