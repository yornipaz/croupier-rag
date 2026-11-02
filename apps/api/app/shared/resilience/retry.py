from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import cast

import httpx
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_exponential_jitter

from app.shared.errors import AppError
from app.shared.logging import get_logger

logger = get_logger(__name__)

RetryPredicate = Callable[[BaseException], bool]


def is_retryable_exception(exc: BaseException) -> bool:
    """Only transient failures: typed retryable errors, timeouts and transport errors."""
    if isinstance(exc, AppError):
        return exc.retryable
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return isinstance(exc, (TimeoutError, ConnectionError))


def _log_retry(retry_state: RetryCallState) -> None:
    outcome = retry_state.outcome
    error = outcome.exception() if outcome is not None else None
    logger.warning(
        "resilience.retry",
        attempt=retry_state.attempt_number,
        error_type=type(error).__name__ if error is not None else None,
        error=str(error) if error is not None else None,
    )


async def call_with_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    base_delay: float,
    max_delay: float,
    should_retry: RetryPredicate = is_retryable_exception,
) -> T:
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    retrying: AsyncRetrying = AsyncRetrying(
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential_jitter(initial=base_delay, max=max_delay, jitter=base_delay / 2),
        retry=retry_if_exception(should_retry),
        before_sleep=_log_retry,
        reraise=True,
    )

    # tenacity only awaits coroutine *functions*; a lambda returning a
    # coroutine would be treated as sync and leak an un-awaited coroutine.
    async def invoke() -> T:
        return await operation()

    return cast(T, await retrying(invoke))


def retry[**P, T](
    *,
    max_retries: int = 3,
    base_delay: float = 0.4,
    max_delay: float = 8.0,
    should_retry: RetryPredicate = is_retryable_exception,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Exponential backoff + jitter, only for retryable errors."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await call_with_retry(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                should_retry=should_retry,
            )

        return wrapper

    return decorator
