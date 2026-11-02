from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import pytest

from app.modules.ai.infrastructure.fastembed_embedding import (
    FastEmbedEmbedding,
    list_multilingual_models,
)
from app.modules.vector_store.application.dto.search import SparseVector
from app.modules.vector_store.infrastructure.fastembed_bm25 import FastEmbedBM25
from app.shared.errors import ConfigurationError


class FakeSparseModel:
    def embed(self, documents: Sequence[str]) -> list[Any]:
        return [
            type(
                "SparseEmbedding",
                (),
                {"indices": [1, 2], "values": [0.5, 0.25]},
            )()
            for _ in documents
        ]


class FakeDenseModel:
    def embed(self, documents: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in documents]


def test_multilingual_models_include_the_default() -> None:
    models = list_multilingual_models()

    assert "sentence-transformers/paraphrase-multilingual-mpnet-base-v2" in models
    assert "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" in models


def test_fastembed_dimension_does_not_download_the_model() -> None:
    embedding = FastEmbedEmbedding(
        model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    )

    assert embedding.dimension == 768


def test_unknown_fastembed_model_fails_fast() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported FastEmbed model"):
        FastEmbedEmbedding(model_name="not/a-real-model")


async def test_dense_embedding_adapter_converts_numpy_like_vectors() -> None:
    embedding = FastEmbedEmbedding(
        model_name="fake",
        dimension=3,
        model=cast(Any, FakeDenseModel()),
    )

    assert await embedding.embed(["uno", "dos"]) == [
        [0.1, 0.2, 0.3],
        [0.1, 0.2, 0.3],
    ]


async def test_bm25_adapter_returns_sparse_vectors() -> None:
    encoder = FastEmbedBM25(model=cast(Any, FakeSparseModel()))

    result = await encoder.embed(["hola"])

    assert result == [SparseVector(indices=[1, 2], values=[0.5, 0.25])]


def test_bm25_rejects_unknown_language() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported BM25 language"):
        FastEmbedBM25(language="klingon")
