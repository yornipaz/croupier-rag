from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.ai.infrastructure.resilient import ResilientEmbedding, ResilientLLM
from app.shared.errors import (
    BadRequestError,
    CircuitOpenError,
    RateLimitedError,
    UpstreamError,
    UpstreamTimeoutError,
)
from app.shared.resilience.circuit_breaker import CircuitBreaker, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FlakyLLM:
    def __init__(self, failures: int, error: Exception) -> None:
        self.calls = 0
        self._failures = failures
        self._error = error
        self.last_schema: ResponseSchema | None = None

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
    ) -> LLMResult:
        _ = prompt, system
        self.calls += 1
        self.last_schema = response_schema
        if self.calls <= self._failures:
            raise self._error
        return LLMResult(text="ok", model="fake")


class SlowLLM:
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
    ) -> LLMResult:
        _ = prompt, system, response_schema
        await asyncio.sleep(1)
        return LLMResult(text="late", model="fake")


class RecoveringLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = True

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
    ) -> LLMResult:
        _ = prompt, system, response_schema
        self.calls += 1
        if self.fail:
            raise UpstreamError("down")
        return LLMResult(text="ok", model="fake")


def _wrapper(inner: Any, *, breaker: CircuitBreaker, max_retries: int = 2) -> ResilientLLM:
    return ResilientLLM(
        inner,
        name="test-llm",
        timeout_s=1.0,
        max_retries=max_retries,
        base_delay_s=0.001,
        max_delay_s=0.005,
        breaker=breaker,
    )


async def test_429_is_retried_then_succeeds() -> None:
    inner = FlakyLLM(failures=2, error=RateLimitedError("quota"))
    breaker = CircuitBreaker("test-llm", failure_threshold=5)

    result = await _wrapper(inner, breaker=breaker).generate("hola", "sistema")

    assert result.text == "ok"
    assert inner.calls == 3
    assert (await breaker.snapshot()).state is CircuitState.CLOSED


async def test_non_retryable_provider_error_is_not_retried() -> None:
    inner = FlakyLLM(failures=1, error=BadRequestError("bad key"))

    with pytest.raises(BadRequestError):
        await _wrapper(inner, breaker=CircuitBreaker("test-llm"), max_retries=3).generate("hola")

    assert inner.calls == 1


async def test_timeout_is_mapped_and_does_not_retry_when_disabled() -> None:
    wrapper = ResilientLLM(
        SlowLLM(),
        name="test-llm",
        timeout_s=0.01,
        max_retries=0,
        base_delay_s=0.001,
        max_delay_s=0.005,
        breaker=CircuitBreaker("test-llm"),
    )

    with pytest.raises(UpstreamTimeoutError):
        await wrapper.generate("hola")


async def test_breaker_opens_after_threshold_and_recovers() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(
        "test-llm",
        failure_threshold=2,
        recovery_timeout=5,
        clock=clock,
    )
    inner = RecoveringLLM()
    wrapper = _wrapper(inner, breaker=breaker, max_retries=0)

    for _ in range(2):
        with pytest.raises(UpstreamError):
            await wrapper.generate("hola")

    assert (await breaker.snapshot()).state is CircuitState.OPEN
    assert inner.calls == 2

    with pytest.raises(CircuitOpenError):
        await wrapper.generate("hola")
    assert inner.calls == 2

    clock.advance(5)
    inner.fail = False

    assert (await wrapper.generate("hola")).text == "ok"
    assert (await breaker.snapshot()).state is CircuitState.CLOSED


class FlakyEmbedding:
    dimension = 2

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 1:
            raise RateLimitedError("quota")
        return [[1.0, 2.0] for _ in texts]


async def test_resilient_embedding_retries_and_preserves_dimension() -> None:
    inner: EmbeddingPort = FlakyEmbedding()
    wrapper = ResilientEmbedding(
        inner,
        name="test-embedding",
        timeout_s=1.0,
        max_retries=1,
        base_delay_s=0.001,
        max_delay_s=0.005,
        breaker=CircuitBreaker("test-embedding"),
    )

    assert wrapper.dimension == 2
    assert await wrapper.embed(["a", "b"]) == [[1.0, 2.0], [1.0, 2.0]]
    assert inner.calls == 2
