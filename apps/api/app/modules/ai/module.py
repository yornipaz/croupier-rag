from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.ai.application.ports.llm import LLMPort
from app.modules.ai.infrastructure.fastembed_embedding import FastEmbedEmbedding
from app.modules.ai.infrastructure.gemini_embedding import GeminiEmbedding
from app.modules.ai.infrastructure.gemini_llm import GeminiLLM
from app.modules.ai.infrastructure.ollama_embedding import OllamaEmbedding
from app.modules.ai.infrastructure.ollama_llm import OllamaLLM
from app.modules.ai.infrastructure.openai_llm import OpenAILLM
from app.modules.ai.infrastructure.resilient import ResilientEmbedding, ResilientLLM
from app.modules.ai.presentation.router import router
from app.shared.errors import (
    EmbeddingNotConfiguredError,
    LLMNotConfiguredError,
)
from app.shared.resilience.circuit_breaker import CircuitBreaker

__all__ = [
    "EmbeddingPort",
    "LLMPort",
    "build_ai_module",
    "build_ai_router",
    "build_embedding",
    "build_llm",
    "router",
]


def _gemini_key(settings: Settings) -> str:
    if settings.gemini_api_key is None:
        raise LLMNotConfiguredError("GEMINI_API_KEY is required")
    return settings.gemini_api_key.get_secret_value()


def _openai_key(settings: Settings) -> str:
    if settings.openai_api_key is None:
        raise LLMNotConfiguredError("OPENAI_API_KEY is required")
    return settings.openai_api_key.get_secret_value()


def build_llm(settings: Settings, *, breaker: CircuitBreaker | None = None) -> LLMPort:
    """Select the LLM adapter from ``LLM_PROVIDER`` and wrap it with resilience."""
    if settings.llm_provider == "gemini":
        if not settings.llm_configured:
            raise LLMNotConfiguredError("GEMINI_API_KEY is required for LLM_PROVIDER=gemini")
        inner: LLMPort = GeminiLLM(api_key=_gemini_key(settings), model=settings.llm_model)
        name = f"llm:gemini:{settings.llm_model}"
    elif settings.llm_provider == "ollama":
        inner = OllamaLLM(
            base_url=settings.ollama_base_url,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
        )
        name = f"llm:ollama:{settings.llm_model}"
    elif settings.llm_provider == "openai":
        if not settings.llm_configured:
            raise LLMNotConfiguredError("OPENAI_API_KEY is required for LLM_PROVIDER=openai")
        inner = OpenAILLM(
            api_key=_openai_key(settings),
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
        )
        name = f"llm:openai:{settings.llm_model}"
    else:  # pragma: no cover - Settings validates the literal
        raise LLMNotConfiguredError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    return ResilientLLM(
        inner,
        name=name,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.http_max_retries,
        base_delay_s=settings.http_retry_base_s,
        max_delay_s=settings.http_retry_max_s,
        breaker=breaker,
        failure_threshold=settings.breaker_failure_threshold,
        recovery_timeout=settings.breaker_recovery_s,
    )


def build_embedding(
    settings: Settings,
    *,
    breaker: CircuitBreaker | None = None,
) -> EmbeddingPort:
    """Select the dense embedding adapter from ``EMBEDDING_PROVIDER``."""
    if settings.embedding_provider == "fastembed":
        inner: EmbeddingPort = FastEmbedEmbedding(model_name=settings.embedding_model)
        name = f"embedding:fastembed:{settings.embedding_model}"
    elif settings.embedding_provider == "ollama":
        inner = OllamaEmbedding(
            base_url=settings.ollama_base_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dim,
            timeout_s=settings.embedding_timeout_s,
        )
        name = f"embedding:ollama:{settings.embedding_model}"
    elif settings.embedding_provider == "gemini":
        if settings.gemini_api_key is None:
            raise EmbeddingNotConfiguredError(
                "GEMINI_API_KEY is required for EMBEDDING_PROVIDER=gemini"
            )
        inner = GeminiEmbedding(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimension=settings.embedding_dim,
        )
        name = f"embedding:gemini:{settings.embedding_model}"
    else:  # pragma: no cover - Settings validates the literal
        raise EmbeddingNotConfiguredError(
            f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}"
        )

    return ResilientEmbedding(
        inner,
        name=name,
        timeout_s=settings.embedding_timeout_s,
        max_retries=settings.http_max_retries,
        base_delay_s=settings.http_retry_base_s,
        max_delay_s=settings.http_retry_max_s,
        breaker=breaker,
        failure_threshold=settings.breaker_failure_threshold,
        recovery_timeout=settings.breaker_recovery_s,
    )


def build_ai_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_ai_module(settings: Settings) -> APIRouter:
    return build_ai_router(settings)
