from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.modules.health.application.dto.health import ProbeResult
from app.shared.logging import get_logger

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from redis.asyncio import Redis

logger = get_logger(__name__)


def _detail(exc: BaseException) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message[:180]}" if message else type(exc).__name__


class RedisHealthProbe:
    name = "redis"
    critical = True

    def __init__(self, client: Redis, *, timeout_seconds: float = 2.0) -> None:
        self._client = client
        self._timeout = timeout_seconds

    async def check(self) -> ProbeResult:
        try:
            pong = await asyncio.wait_for(self._client.ping(), timeout=self._timeout)
        except Exception as exc:
            logger.warning("health.redis.unavailable", error=_detail(exc))
            return ProbeResult(name=self.name, ok=False, detail=_detail(exc))
        return ProbeResult(name=self.name, ok=bool(pong))


class QdrantHealthProbe:
    name = "qdrant"
    critical = True

    def __init__(self, client: AsyncQdrantClient, *, timeout_seconds: float = 2.0) -> None:
        self._client = client
        self._timeout = timeout_seconds

    async def check(self) -> ProbeResult:
        try:
            await asyncio.wait_for(self._client.get_collections(), timeout=self._timeout)
        except Exception as exc:
            logger.warning("health.qdrant.unavailable", error=_detail(exc))
            return ProbeResult(name=self.name, ok=False, detail=_detail(exc))
        return ProbeResult(name=self.name, ok=True)
