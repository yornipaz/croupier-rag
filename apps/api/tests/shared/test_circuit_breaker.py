from __future__ import annotations

import asyncio

import pytest

from app.shared.errors import CircuitOpenError, UpstreamError
from app.shared.resilience.circuit_breaker import CircuitBreaker, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def _boom() -> None:
    raise UpstreamError("upstream down")


async def test_opens_after_threshold_and_short_circuits() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("llm", failure_threshold=2, recovery_timeout=10, clock=clock)

    for _ in range(2):
        with pytest.raises(UpstreamError):
            await breaker.call(_boom)

    snapshot = await breaker.snapshot()
    assert snapshot.state is CircuitState.OPEN
    assert snapshot.failures == 2

    with pytest.raises(CircuitOpenError) as caught:
        await breaker.call(_boom)
    assert caught.value.retry_after == 10
    assert caught.value.details["breaker"] == "llm"


async def test_half_open_success_closes_the_circuit() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("llm", failure_threshold=1, recovery_timeout=5, clock=clock)

    with pytest.raises(UpstreamError):
        await breaker.call(_boom)

    clock.advance(5)

    async def ok() -> str:
        return "ok"

    assert await breaker.call(ok) == "ok"
    assert (await breaker.snapshot()).state is CircuitState.CLOSED


async def test_half_open_failure_reopens_the_circuit() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("llm", failure_threshold=1, recovery_timeout=5, clock=clock)

    with pytest.raises(UpstreamError):
        await breaker.call(_boom)

    clock.advance(5)
    with pytest.raises(UpstreamError):
        await breaker.call(_boom)

    snapshot = await breaker.snapshot()
    assert snapshot.state is CircuitState.OPEN
    assert snapshot.opened_at == clock.now


async def test_ignored_failures_do_not_open_the_circuit() -> None:
    breaker = CircuitBreaker("llm", failure_threshold=1, recovery_timeout=5)

    async def bad_request() -> None:
        raise ValueError("client error")

    with pytest.raises(ValueError, match="client error"):
        await breaker.call(bad_request, should_count=lambda _exc: False)

    assert (await breaker.snapshot()).state is CircuitState.CLOSED


async def test_half_open_allows_only_one_probe_call() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("llm", failure_threshold=1, recovery_timeout=5, clock=clock)

    with pytest.raises(UpstreamError):
        await breaker.call(_boom)

    clock.advance(5)
    release = asyncio.Event()

    async def slow() -> str:
        await release.wait()
        return "ok"

    first = asyncio.create_task(breaker.call(slow))
    await asyncio.sleep(0)

    with pytest.raises(CircuitOpenError):
        await breaker.call(slow)

    release.set()
    assert await first == "ok"
    assert (await breaker.snapshot()).state is CircuitState.CLOSED


async def test_reset_returns_to_closed() -> None:
    breaker = CircuitBreaker("llm", failure_threshold=1)
    with pytest.raises(UpstreamError):
        await breaker.call(_boom)

    await breaker.reset()

    snapshot = await breaker.snapshot()
    assert snapshot.state is CircuitState.CLOSED
    assert snapshot.failures == 0
