from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps

from app.shared.errors import UpstreamTimeoutError
from app.shared.resilience.circuit_breaker import CircuitBreaker
from app.shared.resilience.retry import call_with_retry, is_retryable_exception


@dataclass(frozen=True, slots=True)
class ResiliencePolicy:
    name: str
    timeout_seconds: float
    max_retries: int
    base_delay_seconds: float
    max_delay_seconds: float
    breaker: CircuitBreaker


async def run_resilient[T](
    operation: Callable[[], Awaitable[T]],
    policy: ResiliencePolicy,
) -> T:
    """Timeout per attempt + exponential retry + circuit breaker around one operation."""

    async def attempt() -> T:
        try:
            async with asyncio.timeout(policy.timeout_seconds):
                return await operation()
        except TimeoutError as exc:
            raise UpstreamTimeoutError(
                f"'{policy.name}' timed out after {policy.timeout_seconds}s",
                details={"operation": policy.name},
            ) from exc

    async def with_retry() -> T:
        return await call_with_retry(
            attempt,
            max_retries=policy.max_retries,
            base_delay=policy.base_delay_seconds,
            max_delay=policy.max_delay_seconds,
        )

    return await policy.breaker.call(with_retry, should_count=is_retryable_exception)


def resilient[**P, T](
    *,
    name: str,
    breaker: CircuitBreaker,
    timeout_s: float,
    max_retries: int = 3,
    base_delay_s: float = 0.4,
    max_delay_s: float = 8.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Compose timeout + retry + circuit breaker around an async callable.

    Usage (not wired yet, adapters will use it in later phases):

        breaker = CircuitBreaker("gemini", failure_threshold=5, recovery_timeout=30)

        @resilient(name="gemini", breaker=breaker, timeout_s=60)
        async def generate(prompt: str) -> str: ...
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")

    policy = ResiliencePolicy(
        name=name,
        timeout_seconds=timeout_s,
        max_retries=max_retries,
        base_delay_seconds=base_delay_s,
        max_delay_seconds=max_delay_s,
        breaker=breaker,
    )

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await run_resilient(lambda: func(*args, **kwargs), policy)

        return wrapper

    return decorator
