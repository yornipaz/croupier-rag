from __future__ import annotations

import asyncio
import math
from collections import defaultdict

from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.retrieval.application.dto.retrieval import (
    ImageAsset,
    RetrievalDebug,
    RetrievalDebugHit,
    RetrievalResult,
    RetrievedChunk,
    RetrievedImage,
)
from app.modules.retrieval.application.ports.image_catalog import ImageCatalogPort
from app.modules.retrieval.application.ports.image_url_builder import ImageUrlBuilderPort
from app.modules.retrieval.domain.lexical import lexical_coverage
from app.modules.vector_store.application.dto.search import SparseVector
from app.modules.vector_store.application.ports.sparse_encoder import SparseEncoderPort
from app.modules.vector_store.application.ports.vector_store import VectorStorePort
from app.shared.chunks import BBox
from app.shared.errors import BadRequestError, UpstreamError


class RetrieveContextUseCase:
    """Embed the query, run hybrid search and resolve linked images."""

    def __init__(
        self,
        embedding: EmbeddingPort,
        sparse_encoder: SparseEncoderPort,
        vectors: VectorStorePort,
        images: ImageCatalogPort,
        image_urls: ImageUrlBuilderPort,
        *,
        default_top_k: int,
    ) -> None:
        if default_top_k < 1:
            raise ValueError("default_top_k must be >= 1")
        self._embedding = embedding
        self._sparse_encoder = sparse_encoder
        self._vectors = vectors
        self._images = images
        self._image_urls = image_urls
        self._default_top_k = default_top_k

    async def execute(
        self,
        query: str,
        doc_id: str | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise BadRequestError("query must not be blank")
        limit = top_k if top_k is not None else self._default_top_k
        if limit < 1:
            raise BadRequestError("top_k must be >= 1")
        if limit > 100:
            raise BadRequestError("top_k must be <= 100")

        warmup = getattr(self._embedding, "warmup", None)
        if callable(warmup):
            await warmup()

        dense_vectors, sparse_vectors = await asyncio.gather(
            self._embedding.embed([normalized_query]),
            self._sparse_encoder.embed([normalized_query]),
        )
        if not dense_vectors or not sparse_vectors:
            raise UpstreamError("Embedding adapters returned no vector for the query")
        dense = dense_vectors[0]
        sparse: SparseVector = sparse_vectors[0]

        hits = await self._vectors.hybrid_search(
            dense,
            sparse,
            limit,
            doc_id=doc_id,
        )
        chunks = tuple(
            RetrievedChunk(
                chunk=hit.chunk,
                score=float(hit.score),
                relevance_score=_relevance_score(hit.score, hit.dense_score),
                dense_rank=hit.dense_rank,
                sparse_rank=hit.sparse_rank,
                dense_score=hit.dense_score,
                sparse_score=hit.sparse_score,
                dense_cosine=hit.dense_cosine,
            )
            for hit in hits
        )
        top_score = max((item.relevance_score for item in chunks), default=0.0)
        images = await self._resolve_images(chunks)
        coverage = lexical_coverage(
            sparse.indices,
            [hit.sparse_indices for hit in hits],
        )
        debug = RetrievalDebug(
            retrieved=tuple(
                RetrievalDebugHit(
                    chunk_id=item.chunk.id,
                    doc_id=item.chunk.doc_id,
                    page=item.chunk.page,
                    section_path=item.chunk.section_path,
                    kind=item.chunk.kind,
                    rrf_score=item.score,
                    relevance_score=item.relevance_score,
                    dense_rank=item.dense_rank,
                    sparse_rank=item.sparse_rank,
                    dense_score=item.dense_score,
                    sparse_score=item.sparse_score,
                    dense_cosine=item.dense_cosine,
                )
                for item in chunks
            ),
            lexical_coverage=coverage,
        )
        return RetrievalResult(
            chunks=chunks,
            images=tuple(images),
            top_score=top_score,
            debug=debug,
        )

    async def _resolve_images(
        self,
        chunks: tuple[RetrievedChunk, ...],
    ) -> list[RetrievedImage]:
        references: dict[tuple[str, str], list[tuple[int, RetrievedChunk]]] = defaultdict(list)
        image_ids_by_doc: dict[str, set[str]] = defaultdict(set)
        for index, item in enumerate(chunks, start=1):
            for image_id in item.chunk.image_ids:
                references[(item.chunk.doc_id, image_id)].append((index, item))
                image_ids_by_doc[item.chunk.doc_id].add(image_id)

        if not references:
            return []

        document_ids = tuple(image_ids_by_doc)
        catalogs = await asyncio.gather(
            *(
                self._images.get_many(document_id, tuple(image_ids_by_doc[document_id]))
                for document_id in document_ids
            )
        )
        assets: dict[tuple[str, str], ImageAsset] = {}
        for document_id, catalog in zip(document_ids, catalogs, strict=True):
            for image_id, found_asset in catalog.items():
                assets[(document_id, image_id)] = found_asset

        images: list[RetrievedImage] = []
        for (document_id, image_id), refs in references.items():
            asset = assets.get((document_id, image_id))
            page = asset.page if asset is not None else refs[0][1].chunk.page
            bbox = asset.bbox if asset is not None else refs[0][1].chunk.bbox
            best_score = max(reference[1].relevance_score for reference in refs)
            distance = min(_bbox_distance(reference[1].chunk.bbox, bbox) for reference in refs)
            images.append(
                RetrievedImage(
                    document_id=document_id,
                    image_id=image_id,
                    page=page,
                    bbox=bbox,
                    url=self._image_urls.build(document_id, page, bbox),
                    score=best_score,
                    distance_pt=distance,
                    source_indexes=tuple(sorted({reference[0] for reference in refs})),
                )
            )
        images.sort(
            key=lambda image: (
                -image.score,
                image.distance_pt,
                image.page,
                image.image_id,
            )
        )
        return images


def _relevance_score(rrf_score: float, dense_score: float | None) -> float:
    """Prefer the normalized dense cosine for the defensive threshold.

    Qdrant's RRF score is rank-based and can be high even for an unrelated top
    hit, so it is a poor absolute relevance signal. The dense cosine is in
    [0, 1] and matches ``RETRIEVAL_MIN_SCORE``. Fall back to the fused score
    for fake stores/tests or hits without a dense component.
    """
    if dense_score is not None:
        return float(dense_score)
    return float(rrf_score)


def _bbox_distance(first: BBox, second: BBox) -> float:
    dx = max(first[0] - second[2], second[0] - first[2], 0.0)
    dy = max(first[1] - second[3], second[1] - first[3], 0.0)
    return math.hypot(dx, dy)
