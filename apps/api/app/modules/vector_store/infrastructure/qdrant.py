from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, cast

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.vector_store.application.dto.search import SearchHit, SparseVector
from app.modules.vector_store.application.ports.sparse_encoder import SparseEncoderPort
from app.modules.vector_store.infrastructure.errors import map_qdrant_exception
from app.shared.chunks import Chunk, ChunkKind
from app.shared.errors import UpstreamError
from app.shared.logging import get_logger

logger = get_logger(__name__)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def _chunk_payload(chunk: Chunk) -> dict[str, Any]:
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


def _chunk_from_payload(payload: dict[str, Any]) -> Chunk:
    bbox = payload.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("chunk payload has an invalid bbox")
    kind = payload.get("kind")
    if kind not in ("text", "table", "caption"):
        raise ValueError("chunk payload has an invalid kind")
    section_path = payload.get("section_path") or []
    image_ids = payload.get("image_ids") or []
    if not isinstance(section_path, (list, tuple)) or not isinstance(image_ids, (list, tuple)):
        raise ValueError("chunk payload has invalid list fields")
    return Chunk(
        id=str(payload["id"]),
        doc_id=str(payload["doc_id"]),
        page=int(payload["page"]),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        section_path=tuple(str(part) for part in section_path),
        kind=cast(ChunkKind, kind),
        text=str(payload["text"]),
        image_ids=tuple(str(image_id) for image_id in image_ids),
        token_count=int(payload["token_count"]),
    )


def _rank_map(points: Sequence[qm.ScoredPoint]) -> dict[str, int]:
    return {str(point.id): rank for rank, point in enumerate(points, start=1)}


def _score_map(points: Sequence[qm.ScoredPoint]) -> dict[str, float]:
    return {str(point.id): float(point.score) for point in points}


class QdrantVectorStore:
    """Qdrant adapter with named dense/sparse vectors and server-side RRF fusion."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        *,
        collection_name: str,
        embedding: EmbeddingPort,
        sparse_encoder: SparseEncoderPort,
        prefetch_limit: int = 30,
        upsert_batch_size: int = 64,
    ) -> None:
        if prefetch_limit < 1:
            raise ValueError("prefetch_limit must be >= 1")
        if upsert_batch_size < 1:
            raise ValueError("upsert_batch_size must be >= 1")
        self._client = client
        self._collection_name = collection_name
        self._embedding = embedding
        self._sparse_encoder = sparse_encoder
        self._prefetch_limit = prefetch_limit
        self._upsert_batch_size = upsert_batch_size
        self._ensure_lock = asyncio.Lock()

    async def ensure_collection(self) -> None:
        try:
            async with self._ensure_lock:
                exists = await self._client.collection_exists(self._collection_name)
                if not exists:
                    await self._client.create_collection(
                        collection_name=self._collection_name,
                        vectors_config={
                            DENSE_VECTOR_NAME: qm.VectorParams(
                                size=self._embedding.dimension,
                                distance=qm.Distance.COSINE,
                            )
                        },
                        sparse_vectors_config={
                            SPARSE_VECTOR_NAME: qm.SparseVectorParams(
                                modifier=qm.Modifier.IDF,
                            )
                        },
                    )
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name="doc_id",
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name="page",
                    field_schema=qm.PayloadSchemaType.INTEGER,
                    wait=True,
                )
        except Exception as exc:
            raise map_qdrant_exception(exc) from exc

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        items = list(chunks)
        if not items:
            return
        try:
            dense_vectors = await self._embedding.embed([chunk.text for chunk in items])
            sparse_vectors = await self._sparse_encoder.embed([chunk.text for chunk in items])
            if len(dense_vectors) != len(items) or len(sparse_vectors) != len(items):
                raise UpstreamError("Embedding adapters returned a different number of vectors")

            for start in range(0, len(items), self._upsert_batch_size):
                batch = items[start : start + self._upsert_batch_size]
                points = [
                    qm.PointStruct(
                        id=chunk.id,
                        vector={
                            DENSE_VECTOR_NAME: dense_vectors[start + offset],
                            SPARSE_VECTOR_NAME: qm.SparseVector(
                                indices=sparse_vectors[start + offset].indices,
                                values=sparse_vectors[start + offset].values,
                            ),
                        },
                        payload=_chunk_payload(chunk),
                    )
                    for offset, chunk in enumerate(batch)
                ]
                await self._client.upsert(
                    collection_name=self._collection_name,
                    points=points,
                    wait=True,
                )
        except Exception as exc:
            raise map_qdrant_exception(exc) from exc

    async def hybrid_search(
        self,
        dense: Sequence[float],
        sparse: SparseVector,
        top_k: int,
        doc_id: str | None = None,
    ) -> list[SearchHit]:
        if top_k < 1:
            return []
        prefetch_limit = max(self._prefetch_limit, top_k)
        query_filter = (
            qm.Filter(
                must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
            )
            if doc_id
            else None
        )
        qdrant_sparse = qm.SparseVector(indices=sparse.indices, values=sparse.values)
        prefetch = [
            qm.Prefetch(
                query=list(dense),
                using=DENSE_VECTOR_NAME,
                filter=query_filter,
                limit=prefetch_limit,
            ),
            qm.Prefetch(
                query=qdrant_sparse,
                using=SPARSE_VECTOR_NAME,
                filter=query_filter,
                limit=prefetch_limit,
            ),
        ]
        requests = [
            qm.QueryRequest(
                prefetch=prefetch,
                query=qm.FusionQuery(fusion=qm.Fusion.RRF),
                limit=top_k,
                with_payload=True,
                filter=query_filter,
            ),
            qm.QueryRequest(
                query=list(dense),
                using=DENSE_VECTOR_NAME,
                limit=prefetch_limit,
                with_payload=False,
                filter=query_filter,
            ),
            qm.QueryRequest(
                query=qdrant_sparse,
                using=SPARSE_VECTOR_NAME,
                limit=prefetch_limit,
                with_payload=False,
                filter=query_filter,
            ),
        ]

        try:
            responses = await self._client.query_batch_points(
                collection_name=self._collection_name,
                requests=requests,
            )
        except Exception as exc:
            raise map_qdrant_exception(exc) from exc

        if len(responses) != 3:
            raise UpstreamError("Qdrant returned an unexpected batch query response")

        fused_points = responses[0].points
        dense_points = responses[1].points
        sparse_points = responses[2].points
        dense_ranks = _rank_map(dense_points)
        sparse_ranks = _rank_map(sparse_points)
        dense_scores = _score_map(dense_points)
        sparse_scores = _score_map(sparse_points)

        hits: list[SearchHit] = []
        for point in fused_points:
            if not isinstance(point.payload, dict):
                raise UpstreamError("Qdrant returned a hit without its chunk payload")
            try:
                chunk = _chunk_from_payload(point.payload)
            except (KeyError, TypeError, ValueError) as exc:
                raise UpstreamError("Qdrant returned an invalid chunk payload") from exc
            point_id = str(point.id)
            hits.append(
                SearchHit(
                    chunk=chunk,
                    score=float(point.score),
                    dense_rank=dense_ranks.get(point_id),
                    sparse_rank=sparse_ranks.get(point_id),
                    dense_score=dense_scores.get(point_id),
                    sparse_score=sparse_scores.get(point_id),
                )
            )
        return hits

    async def delete_by_doc(self, doc_id: str) -> None:
        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="doc_id",
                                match=qm.MatchValue(value=doc_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:
            raise map_qdrant_exception(exc) from exc
