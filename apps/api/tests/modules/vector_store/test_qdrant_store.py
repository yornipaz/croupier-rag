from __future__ import annotations

import uuid
from typing import Any, cast

import httpx
import pytest
from qdrant_client.http import exceptions as qdrant_exceptions
from qdrant_client.http import models as qm

from app.modules.vector_store.application.dto.search import SparseVector
from app.modules.vector_store.infrastructure.qdrant import QdrantVectorStore
from app.shared.chunks import Chunk
from app.shared.errors import UpstreamError


class FakeEmbedding:
    dimension = 3

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeSparseEncoder:
    async def embed(self, texts: list[str]) -> list[SparseVector]:
        return [SparseVector(indices=[1, 2], values=[0.5, 0.25]) for _ in texts]


class FakeQdrantClient:
    def __init__(
        self,
        *,
        fused: list[qm.ScoredPoint] | None = None,
        dense: list[qm.ScoredPoint] | None = None,
        sparse: list[qm.ScoredPoint] | None = None,
    ) -> None:
        self.exists = False
        self.create_calls = 0
        self.created: dict[str, Any] | None = None
        self.indexes: list[dict[str, Any]] = []
        self.upserts: list[dict[str, Any]] = []
        self.requests: list[qm.QueryRequest] | None = None
        self.deleted: dict[str, Any] | None = None
        self._fused = fused or []
        self._dense = dense or []
        self._sparse = sparse or []

    async def collection_exists(self, collection_name: str) -> bool:
        _ = collection_name
        return self.exists

    async def create_collection(self, **kwargs: Any) -> None:
        self.create_calls += 1
        self.created = kwargs
        self.exists = True

    async def create_payload_index(self, **kwargs: Any) -> None:
        self.indexes.append(kwargs)

    async def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)

    async def query_batch_points(
        self,
        collection_name: str,
        requests: list[qm.QueryRequest],
    ) -> list[qm.QueryResponse]:
        _ = collection_name
        self.requests = requests
        return [
            qm.QueryResponse(points=self._fused),
            qm.QueryResponse(points=self._dense),
            qm.QueryResponse(points=self._sparse),
        ]

    async def delete(self, **kwargs: Any) -> None:
        self.deleted = kwargs


def _chunk(index: int, *, doc_id: str = "doc-1") -> Chunk:
    return Chunk(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"chunk-{index}")),
        doc_id=doc_id,
        page=index + 1,
        bbox=(10.0, 20.0, 30.0, 40.0),
        section_path=("Manual", f"Sección {index}"),
        kind="table" if index == 0 else "text",
        text=f"contenido {index}",
        image_ids=(f"image-{index}",),
        token_count=12 + index,
    )


def _payload(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "doc_id": chunk.doc_id,
        "page": chunk.page,
        "bbox": list(chunk.bbox),
        "section_path": list(chunk.section_path),
        "kind": chunk.kind,
        "text": chunk.text,
        "image_ids": list(chunk.image_ids),
        "token_count": chunk.token_count,
    }


def _store(client: FakeQdrantClient) -> QdrantVectorStore:
    return QdrantVectorStore(
        cast(Any, client),
        collection_name="manual_chunks",
        embedding=cast(Any, FakeEmbedding()),
        sparse_encoder=cast(Any, FakeSparseEncoder()),
        prefetch_limit=20,
    )


async def test_ensure_collection_creates_named_vectors_and_payload_indexes() -> None:
    client = FakeQdrantClient()
    store = _store(client)

    await store.ensure_collection()

    assert client.created is not None
    assert client.created["collection_name"] == "manual_chunks"
    vectors = client.created["vectors_config"]
    assert vectors["dense"].size == 3
    assert vectors["dense"].distance == qm.Distance.COSINE
    sparse = client.created["sparse_vectors_config"]
    assert sparse["sparse"].modifier == qm.Modifier.IDF

    fields = {index["field_name"]: index["field_schema"] for index in client.indexes}
    assert fields == {
        "doc_id": qm.PayloadSchemaType.KEYWORD,
        "page": qm.PayloadSchemaType.INTEGER,
    }
    assert all(index["wait"] is True for index in client.indexes)

    await store.ensure_collection()
    assert client.create_calls == 1


async def test_upsert_embeds_and_stores_the_full_chunk_payload() -> None:
    client = FakeQdrantClient()
    store = _store(client)
    chunk = _chunk(0)

    await store.upsert([chunk])

    assert len(client.upserts) == 1
    points = client.upserts[0]["points"]
    assert len(points) == 1
    point = points[0]
    assert point.id == chunk.id
    assert point.vector["dense"] == [0.1, 0.2, 0.3]
    assert point.vector["sparse"] == qm.SparseVector(indices=[1, 2], values=[0.5, 0.25])
    assert point.payload == _payload(chunk)
    assert client.upserts[0]["wait"] is True


async def test_hybrid_search_uses_prefetch_rrf_and_returns_component_ranks() -> None:
    first = _chunk(0)
    second = _chunk(1)
    fused = [
        qm.ScoredPoint(id=first.id, version=0, score=0.032, payload=_payload(first)),
        qm.ScoredPoint(id=second.id, version=0, score=0.016, payload=_payload(second)),
    ]
    dense = [
        qm.ScoredPoint(id=first.id, version=0, score=0.91),
        qm.ScoredPoint(id=second.id, version=0, score=0.82),
    ]
    sparse = [
        qm.ScoredPoint(id=second.id, version=0, score=7.2),
        qm.ScoredPoint(id=first.id, version=0, score=6.4),
    ]
    client = FakeQdrantClient(fused=fused, dense=dense, sparse=sparse)
    store = _store(client)

    hits = await store.hybrid_search(
        [0.1, 0.2, 0.3],
        SparseVector(indices=[1, 2], values=[0.5, 0.25]),
        top_k=2,
        doc_id="doc-1",
    )

    assert [hit.chunk for hit in hits] == [first, second]
    assert [hit.score for hit in hits] == [0.032, 0.016]
    assert hits[0].dense_rank == 1
    assert hits[0].sparse_rank == 2
    assert hits[1].dense_rank == 2
    assert hits[1].sparse_rank == 1
    assert hits[0].dense_score == 0.91
    assert hits[0].sparse_score == 6.4

    assert client.requests is not None
    fused_request, dense_request, sparse_request = client.requests
    assert isinstance(fused_request.query, qm.FusionQuery)
    assert fused_request.query.fusion == qm.Fusion.RRF
    assert fused_request.prefetch is not None
    assert len(fused_request.prefetch) == 2
    assert fused_request.limit == 2
    assert fused_request.with_payload is True

    assert fused_request.filter is not None
    condition = fused_request.filter.must[0]
    assert condition.key == "doc_id"
    assert condition.match.value == "doc-1"
    assert fused_request.prefetch[0].using == "dense"
    assert fused_request.prefetch[1].using == "sparse"
    assert fused_request.prefetch[0].limit == 20
    assert dense_request.using == "dense"
    assert sparse_request.using == "sparse"
    assert dense_request.limit == 20


async def test_delete_by_doc_uses_a_filter_selector() -> None:
    client = FakeQdrantClient()
    store = _store(client)

    await store.delete_by_doc("doc-1")

    assert client.deleted is not None
    selector = client.deleted["points_selector"]
    assert isinstance(selector, qm.FilterSelector)
    condition = selector.filter.must[0]
    assert condition.key == "doc_id"
    assert condition.match.value == "doc-1"
    assert client.deleted["wait"] is True


class BrokenQdrantClient(FakeQdrantClient):
    async def query_batch_points(
        self,
        collection_name: str,
        requests: list[qm.QueryRequest],
    ) -> list[qm.QueryResponse]:
        _ = collection_name, requests
        raise qdrant_exceptions.UnexpectedResponse(
            status_code=503,
            reason_phrase="Service Unavailable",
            content=b"down",
            headers=httpx.Headers(),
        )


async def test_qdrant_errors_are_mapped_to_app_errors() -> None:
    store = _store(BrokenQdrantClient())

    with pytest.raises(UpstreamError):
        await store.hybrid_search(
            [0.1, 0.2, 0.3],
            SparseVector(indices=[1], values=[1.0]),
            top_k=1,
        )
