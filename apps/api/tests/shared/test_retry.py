from __future__ import annotations

import asyncio

import pytest

from app.shared.errors import (
    CircuitOpenError,
    UpstreamError,
    UpstreamTimeoutError,
    ValidationError,
)
from app.shared.resilience.circuit_breaker import CircuitBreaker
from app.shared.resilience.policy import ResiliencePolicy, resilient, run_resilient
from app.shared.resilience.retry import call_with_retry, retry


async def test_retries_only_retryable_errors() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise UpstreamError("429")
        return "ok"

    result = await call_with_retry(flaky, max_retries=3, base_delay=0.001, max_delay=0.005)

    assert result == "ok"
    assert calls == 3


async def test_retry_decorator_retries_retryable_errors() -> None:
    calls = 0

    @retry(max_retries=2, base_delay=0.001, max_delay=0.005)
    async def flaky(value: int) -> int:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise UpstreamError("503")
        return value * 2

    assert await flaky(21) == 42
    assert calls == 3


async def test_does_not_retry_non_retryable_errors() -> None:
    calls = 0

    async def broken() -> str:
        nonlocal calls
        calls += 1
        raise ValidationError("bad input")

    with pytest.raises(ValidationError):
        await call_with_retry(broken, max_retries=3, base_delay=0.001, max_delay=0.005)

    assert calls == 1


async def test_timeout_is_mapped_to_typed_error() -> None:
    breaker = CircuitBreaker("llm", failure_threshold=5)
    policy = ResiliencePolicy(
        name="llm",
        timeout_seconds=0.01,
        max_retries=0,
        base_delay_seconds=0.001,
        max_delay_seconds=0.005,
        breaker=breaker,
    )

    async def slow() -> str:
        await asyncio.sleep(1)
        return "never"

    with pytest.raises(UpstreamTimeoutError):
        await run_resilient(slow, policy)


async def test_resilient_decorator_composes_timeout() -> None:
    breaker = CircuitBreaker("embeddings", failure_threshold=5)

    @resilient(name="embeddings", breaker=breaker, timeout_s=0.01, max_retries=0)
    async def slow(text: str) -> str:
        await asyncio.sleep(1)
        return text

    with pytest.raises(UpstreamTimeoutError):
        await slow("hola")


async def test_open_breaker_blocks_retries() -> None:
    breaker = CircuitBreaker("llm", failure_threshold=1)
    policy = ResiliencePolicy(
        name="llm",
        timeout_seconds=1,
        max_retries=1,
        base_delay_seconds=0.001,
        max_delay_seconds=0.005,
        breaker=breaker,
    )
    calls = 0

    async def failing() -> str:
        nonlocal calls
        calls += 1
        raise UpstreamError("boom")

    with pytest.raises(UpstreamError):
        await run_resilient(failing, policy)
    assert calls == 2  # one attempt + one retry

    with pytest.raises(CircuitOpenError):
        await run_resilient(failing, policy)
    assert calls == 2


async def test_success_passes_through() -> None:
    breaker = CircuitBreaker("llm", failure_threshold=1)
    policy = ResiliencePolicy(
        name="llm",
        timeout_seconds=1,
        max_retries=2,
        base_delay_seconds=0.001,
        max_delay_seconds=0.005,
        breaker=breaker,
    )

    async def ok() -> int:
        return 42

    assert await run_resilient(ok, policy) == 42
