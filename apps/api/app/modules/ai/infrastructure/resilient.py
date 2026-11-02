from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.ai.application.ports.llm import LLMPort
from app.shared.resilience.circuit_breaker import CircuitBreaker
from app.shared.resilience.policy import resilient


class ResilientLLM:
    """Same ``LLMPort`` contract, wrapped with timeout + retry + breaker."""

    def __init__(
        self,
        inner: LLMPort,
        *,
        name: str,
        timeout_s: float,
        max_retries: int,
        base_delay_s: float,
        max_delay_s: float,
        breaker: CircuitBreaker | None = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._breaker = breaker or CircuitBreaker(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._generate: Callable[..., Awaitable[LLMResult]] = resilient(
            name=name,
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.generate)

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
    ) -> LLMResult:
        return await self._generate(prompt, system, response_schema)


class ResilientEmbedding:
    """Same ``EmbeddingPort`` contract, wrapped with timeout + retry + breaker."""

    def __init__(
        self,
        inner: EmbeddingPort,
        *,
        name: str,
        timeout_s: float,
        max_retries: int,
        base_delay_s: float,
        max_delay_s: float,
        breaker: CircuitBreaker | None = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._inner = inner
        self._breaker = breaker or CircuitBreaker(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._embed: Callable[[Sequence[str]], Awaitable[list[list[float]]]] = resilient(
            name=name,
            breaker=self._breaker,
            timeout_s=timeout_s,
            max_retries=max_retries,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        )(inner.embed)

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def warmup(self) -> None:
        """Delegate an optional warmup to the provider (not retried/timed out)."""
        warmup = getattr(self._inner, "warmup", None)
        if callable(warmup):
            await warmup()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts)
