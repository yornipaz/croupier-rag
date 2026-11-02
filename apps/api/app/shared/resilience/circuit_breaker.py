from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from app.shared.errors import CircuitOpenError
from app.shared.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
FailurePredicate = Callable[[BaseException], bool]


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class BreakerSnapshot:
    name: str
    state: CircuitState
    failures: int
    opened_at: float | None


def _count_everything(_exc: BaseException) -> bool:
    return True


class CircuitBreaker:
    """Small async circuit breaker with an injectable clock (test friendly)."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        return self._state

    async def snapshot(self) -> BreakerSnapshot:
        async with self._lock:
            return BreakerSnapshot(
                name=self._name,
                state=self._state,
                failures=self._failures,
                opened_at=self._opened_at,
            )

    async def reset(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._opened_at = None
            self._half_open_in_flight = 0

    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        should_count: FailurePredicate = _count_everything,
    ) -> T:
        await self._acquire()
        try:
            result = await operation()
        except BaseException as exc:
            count_failure = isinstance(exc, Exception) and should_count(exc)
            await self._release(success=False if count_failure else None)
            raise
        else:
            await self._release(success=True)
            return result

    async def _acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._state is CircuitState.OPEN:
                elapsed = now - (self._opened_at or now)
                if elapsed >= self._recovery_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                else:
                    raise CircuitOpenError(
                        self._name,
                        retry_after=round(self._recovery_timeout - elapsed, 3),
                    )

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self._half_open_max_calls:
                    raise CircuitOpenError(self._name)
                self._half_open_in_flight += 1
                logger.debug("circuit_breaker.half_open_acquired", breaker=self._name)

    async def _release(self, *, success: bool | None) -> None:
        async with self._lock:
            if success is True:
                self._failures = 0
                if self._state is CircuitState.HALF_OPEN:
                    self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                    self._transition(CircuitState.CLOSED)
                return

            if self._state is CircuitState.HALF_OPEN:
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                if success is False:
                    self._trip()
                return

            if success is False and self._state is CircuitState.CLOSED:
                self._failures += 1
                if self._failures >= self._failure_threshold:
                    self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._failures = self._failure_threshold
        self._half_open_in_flight = 0
        logger.warning(
            "circuit_breaker.opened",
            breaker=self._name,
            failures=self._failures,
            recovery_timeout=self._recovery_timeout,
        )

    def _transition(self, new_state: CircuitState) -> None:
        if self._state is new_state:
            return
        previous = self._state
        self._state = new_state
        if new_state is CircuitState.CLOSED:
            self._failures = 0
            self._opened_at = None
            self._half_open_in_flight = 0
        logger.info(
            "circuit_breaker.state_changed",
            breaker=self._name,
            previous=previous.value,
            current=new_state.value,
        )
