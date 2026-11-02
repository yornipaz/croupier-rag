from __future__ import annotations

from app.modules.ingestion.application.ports.jobs import JobRepositoryPort
from app.shared.jobs import Job


class GetJobUseCase:
    def __init__(self, jobs: JobRepositoryPort) -> None:
        self._jobs = jobs

    async def execute(self, job_id: str) -> Job:
        return await self._jobs.get(job_id)
