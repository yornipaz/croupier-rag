from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.modules.retrieval.application.dto.retrieval import ImageAsset
from app.modules.retrieval.application.use_cases.retrieve_context import (
    RetrieveContextUseCase,
)
from app.modules.retrieval.infrastructure.image_catalog import FileSystemImageCatalog
from app.modules.vector_store.application.dto.search import SearchHit, SparseVector
from app.shared.chunks import BBox, Chunk
from app.shared.errors import BadRequestError


class FakeEmbedding:
    dimension = 2

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.queries.extend(texts)
        return [[0.1, 0.2] for _ in texts]


class FakeSparseEncoder:
    async def embed(self, texts: Sequence[str]) -> list[SparseVector]:
        return [SparseVector(indices=[1], values=[1.0]) for _ in texts]


class FakeVectorStore:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str | None, int]] = []

    async def ensure_collection(self) -> None:
        return None

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        _ = chunks

    async def upsert_embedded(self, chunks: Sequence[object]) -> None:
        _ = chunks

    async def hybrid_search(
        self,
        dense: Sequence[float],
        sparse: SparseVector,
        top_k: int,
        doc_id: str | None = None,
    ) -> list[SearchHit]:
        _ = dense, sparse
        self.calls.append((doc_id, top_k))
        return self.hits

    async def delete_by_doc(self, doc_id: str) -> None:
        _ = doc_id


class FakeCatalog:
    def __init__(self, assets: dict[str, ImageAsset]) -> None:
        self.assets = assets

    async def get_many(
        self,
        document_id: str,
        image_ids: Sequence[str],
    ) -> dict[str, ImageAsset]:
        return {
            image_id: self.assets[image_id]
            for image_id in image_ids
            if image_id in self.assets and self.assets[image_id].document_id == document_id
        }


class FakeUrlBuilder:
    def build(self, document_id: str, page: int, bbox: BBox) -> str:
        return f"/crop/{document_id}/{page}/{bbox[0]:.0f}"


def _chunk(
    index: int,
    *,
    doc_id: str = "doc-1",
    page: int = 1,
    bbox: BBox = (50.0, 100.0, 200.0, 120.0),
    image_ids: tuple[str, ...] = (),
) -> Chunk:
    return Chunk(
        id=f"chunk-{index}",
        doc_id=doc_id,
        page=page,
        bbox=bbox,
        section_path=("Manual", f"Sección {index}"),
        kind="text",
        text=f"contenido {index}",
        image_ids=image_ids,
        token_count=10,
    )


def _use_case(
    hits: list[SearchHit],
    assets: dict[str, ImageAsset] | None = None,
) -> tuple[RetrieveContextUseCase, FakeVectorStore]:
    vectors = FakeVectorStore(hits)
    use_case = RetrieveContextUseCase(
        FakeEmbedding(),
        FakeSparseEncoder(),
        vectors,
        FakeCatalog(assets or {}),
        FakeUrlBuilder(),
        default_top_k=8,
    )
    return use_case, vectors


async def test_retrieve_context_resolves_and_deduplicates_images() -> None:
    first = _chunk(1, image_ids=("img-1",))
    second = _chunk(
        2,
        bbox=(50.0, 300.0, 200.0, 320.0),
        image_ids=("img-1", "img-2"),
    )
    hits = [
        SearchHit(
            chunk=second,
            score=0.03,
            dense_score=0.7,
            dense_rank=2,
            sparse_rank=1,
            sparse_indices=(2,),
        ),
        SearchHit(
            chunk=first,
            score=0.02,
            dense_score=0.8,
            dense_rank=1,
            sparse_rank=2,
            sparse_indices=(1, 2),
        ),
    ]
    assets = {
        "img-1": ImageAsset("doc-1", "img-1", 1, (50.0, 130.0, 200.0, 280.0)),
        "img-2": ImageAsset("doc-1", "img-2", 1, (50.0, 330.0, 200.0, 420.0)),
    }
    use_case, vectors = _use_case(hits, assets)

    result = await use_case.execute("¿Cómo se conecta el panel?", top_k=5)

    assert vectors.calls == [(None, 5)]
    assert result.top_score == pytest.approx(0.8)
    assert len(result.chunks) == 2
    assert len(result.images) == 2
    first_image, second_image = result.images
    assert first_image.image_id == "img-1"
    assert first_image.source_indexes == (1, 2)
    assert first_image.score == pytest.approx(0.8)
    assert second_image.image_id == "img-2"
    assert second_image.source_indexes == (1,)
    assert first_image.url.startswith("/crop/doc-1/1/")
    assert result.debug.retrieved[0].rrf_score == pytest.approx(0.03)
    assert result.debug.lexical_coverage == pytest.approx(1.0)


async def test_top_score_uses_dense_similarity_not_rank_rrf() -> None:
    hit = SearchHit(
        chunk=_chunk(1),
        score=0.5,
        dense_score=0.1,
        dense_rank=1,
        sparse_rank=1,
    )
    use_case, _ = _use_case([hit])

    result = await use_case.execute("consulta no relacionada")

    assert result.top_score == pytest.approx(0.1)
    assert result.debug.retrieved[0].rrf_score == pytest.approx(0.5)


async def test_retrieve_context_rejects_blank_query() -> None:
    use_case, _ = _use_case([])

    with pytest.raises(BadRequestError):
        await use_case.execute("   ")


async def test_filesystem_image_catalog_reads_sidecar(tmp_path: Path) -> None:
    image_dir = tmp_path / "images" / "doc-1"
    image_dir.mkdir(parents=True)
    (image_dir / "img-1.json").write_text(
        json.dumps(
            {
                "image_id": "img-1",
                "document_id": "doc-1",
                "page": 3,
                "bbox": [10, 20, 30, 40],
            }
        ),
        encoding="utf-8",
    )
    catalog = FileSystemImageCatalog(tmp_path)

    assets = await catalog.get_many("doc-1", ["img-1", "missing"])

    assert assets == {"img-1": ImageAsset("doc-1", "img-1", 3, (10.0, 20.0, 30.0, 40.0))}
