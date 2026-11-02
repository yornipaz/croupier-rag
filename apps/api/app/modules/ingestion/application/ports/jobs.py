from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.shared.jobs import Job


class JobRepositoryPort(Protocol):
    async def save(self, job: Job) -> None: ...

    async def get(self, job_id: str) -> Job: ...

    async def delete(self, job_id: str) -> None: ...


class JobEventPublisherPort(Protocol):
    async def publish(self, job: Job) -> None: ...


class JobEventSubscriberPort(Protocol):
    def stream(self, job_id: str) -> AsyncIterator[Job]: ...
