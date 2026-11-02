from __future__ import annotations

from typing import Any, cast

import pytest

from app.config.settings import Settings
from app.modules.ai.module import build_embedding, build_llm
from app.modules.vector_store.infrastructure.fastembed_bm25 import FastEmbedBM25
from app.modules.vector_store.module import build_sparse_encoder, build_vector_store
from app.shared.errors import EmbeddingNotConfiguredError, LLMNotConfiguredError


def test_build_llm_requires_gemini_key() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(LLMNotConfiguredError):
        build_llm(settings)


def test_build_llm_selects_ollama_and_exposes_only_the_port() -> None:
    settings = Settings(_env_file=None, llm_provider="ollama", llm_model="llama-test")

    llm = build_llm(settings)

    assert llm.breaker.name == "llm:ollama:llama-test"


def test_build_llm_requires_deepseek_key() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        llm_model="deepseek-flash",
    )

    with pytest.raises(LLMNotConfiguredError):
        build_llm(settings)


def test_build_llm_selects_deepseek() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        llm_model="deepseek-flash",
        deepseek_api_key="sk-test",
    )

    llm = build_llm(settings)

    assert llm.breaker.name == "llm:deepseek:deepseek-flash"


def test_build_embedding_defaults_to_local_multilingual_model() -> None:
    embedding = build_embedding(Settings(_env_file=None))

    assert embedding.dimension == 768


def test_build_embedding_requires_gemini_key() -> None:
    settings = Settings(_env_file=None, embedding_provider="gemini")

    with pytest.raises(EmbeddingNotConfiguredError):
        build_embedding(settings)


def test_build_sparse_encoder_uses_spanish_bm25() -> None:
    encoder = build_sparse_encoder(Settings(_env_file=None))

    assert isinstance(encoder, FastEmbedBM25)


def test_build_vector_store_wraps_the_qdrant_adapter() -> None:
    settings = Settings(_env_file=None)
    embedding = build_embedding(settings)
    sparse_encoder = build_sparse_encoder(settings)
    client = cast(Any, object())

    store = build_vector_store(
        settings,
        client=client,
        embedding=embedding,
        sparse_encoder=sparse_encoder,
    )

    assert store.breaker.name.startswith("vector-store:qdrant:")
