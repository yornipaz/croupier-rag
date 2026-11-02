from __future__ import annotations

from datetime import datetime

from app.shared.jobs import Job, JobStatus
from app.shared.schemas import CamelModel


class JobSchema(CamelModel):
    job_id: str
    doc_id: str
    status: JobStatus
    stage: str
    progress: int
    error: str | None = None
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> JobSchema:
        return cls(
            job_id=job.job_id,
            doc_id=job.doc_id,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            error=job.error,
            updated_at=job.updated_at,
        )
