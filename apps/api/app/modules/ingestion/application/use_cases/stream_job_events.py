from __future__ import annotations

from collections.abc import AsyncIterator

from app.modules.ingestion.application.ports.jobs import (
    JobEventSubscriberPort,
    JobRepositoryPort,
)
from app.shared.jobs import Job


class StreamJobEventsUseCase:
    def __init__(
        self,
        jobs: JobRepositoryPort,
        events: JobEventSubscriberPort,
    ) -> None:
        self._jobs = jobs
        self._events = events

    async def get_current(self, job_id: str) -> Job:
        return await self._jobs.get(job_id)

    async def events(self, job_id: str) -> AsyncIterator[Job]:
        async for job in self._events.stream(job_id):
            yield job

    async def execute(self, job_id: str) -> AsyncIterator[Job]:
        yield await self.get_current(job_id)
        async for job in self.events(job_id):
            yield job
