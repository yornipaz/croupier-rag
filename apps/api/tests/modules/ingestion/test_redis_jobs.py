from __future__ import annotations

from typing import Any, cast

import pytest
from redis.asyncio import Redis

from app.modules.ingestion.infrastructure.redis_jobs import (
    RedisJobEventPublisher,
    RedisJobRepository,
)
from app.shared.errors import JobNotFoundError
from app.shared.jobs import Job, job_from_json, job_to_json


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.published: list[tuple[str, str]] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        _ = ex
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


def _redis() -> tuple[FakeRedis, Redis]:
    fake = FakeRedis()
    return fake, cast(Any, fake)


def _job() -> Job:
    return Job(
        job_id="job-1",
        doc_id="doc-1",
        status="PENDING",
        stage="queued",
        progress=0,
    )


def test_job_json_roundtrip() -> None:
    job = _job()
    restored = job_from_json(job_to_json(job))

    assert restored.job_id == job.job_id
    assert restored.status == "PENDING"
    assert restored.updated_at == job.updated_at


async def test_redis_repository_and_publisher() -> None:
    fake, redis = _redis()
    repository = RedisJobRepository(redis, prefix="job:", ttl_seconds=60)
    publisher = RedisJobEventPublisher(redis, prefix="events:")

    await repository.save(_job())
    restored = await repository.get("job-1")
    assert restored.job_id == "job-1"

    await publisher.publish(restored)
    assert fake.published[0][0] == "events:job-1"
    assert '"job_id":"job-1"' in fake.published[0][1]

    await repository.delete("job-1")
    with pytest.raises(JobNotFoundError):
        await repository.get("job-1")
