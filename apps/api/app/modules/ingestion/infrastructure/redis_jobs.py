from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

from app.shared.errors import JobNotFoundError, UpstreamError
from app.shared.jobs import Job, job_from_json, job_to_json
from app.shared.logging import get_logger

logger = get_logger(__name__)


class RedisJobRepository:
    def __init__(self, redis: Redis, *, prefix: str, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        self._redis = redis
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    async def save(self, job: Job) -> None:
        try:
            await self._redis.set(
                self._key(job.job_id),
                job_to_json(job),
                ex=self._ttl_seconds,
            )
        except Exception as exc:
            raise UpstreamError(
                "Could not persist job state",
                details={"errorType": type(exc).__name__},
            ) from exc

    async def get(self, job_id: str) -> Job:
        try:
            raw = await self._redis.get(self._key(job_id))
        except Exception as exc:
            raise UpstreamError(
                "Could not read job state",
                details={"errorType": type(exc).__name__},
            ) from exc
        if raw is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        try:
            return job_from_json(raw)
        except (TypeError, ValueError) as exc:
            raise UpstreamError("Job state is corrupted") from exc

    async def delete(self, job_id: str) -> None:
        try:
            await self._redis.delete(self._key(job_id))
        except Exception as exc:
            raise UpstreamError(
                "Could not delete job state",
                details={"errorType": type(exc).__name__},
            ) from exc

    def _key(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}"


class RedisJobEventPublisher:
    def __init__(self, redis: Redis, *, prefix: str) -> None:
        self._redis = redis
        self._prefix = prefix

    async def publish(self, job: Job) -> None:
        try:
            await self._redis.publish(self._channel(job.job_id), job_to_json(job))
        except Exception as exc:
            raise UpstreamError(
                "Could not publish job event",
                details={"errorType": type(exc).__name__},
            ) from exc

    def _channel(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}"


class RedisJobEventSubscriber:
    def __init__(self, redis: Redis, *, prefix: str) -> None:
        self._redis = redis
        self._prefix = prefix

    async def stream(self, job_id: str) -> AsyncIterator[Job]:
        channel = f"{self._prefix}{job_id}"
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(channel)
            while True:
                message: Any = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    continue
                data = message.get("data") if isinstance(message, dict) else None
                if data is None:
                    continue
                try:
                    yield job_from_json(data)
                except (TypeError, ValueError):
                    logger.warning("ingestion.job_event_skipped", channel=channel)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                logger.debug("ingestion.job_event_unsubscribe_failed", channel=channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]
