from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.ingestion.presentation.router import (
    get_get_job_use_case,
    get_stream_job_events_use_case,
    router,
)
from app.shared.errors import JobNotFoundError
from app.shared.exception_handlers import register_exception_handlers
from app.shared.jobs import Job, JobStatus


class FakeGetJob:
    def __init__(self, job: Job) -> None:
        self.job = job

    async def execute(self, job_id: str) -> Job:
        if job_id != self.job.job_id:
            raise JobNotFoundError("missing")
        return self.job


class FakeStreamJobs:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    async def get_current(self, job_id: str) -> Job:
        _ = job_id
        return self.jobs[0]

    async def events(self, job_id: str) -> AsyncIterator[Job]:
        _ = job_id
        for job in self.jobs[1:]:
            yield job


def _job(status: JobStatus = "PROCESSING") -> Job:
    return Job(
        job_id="job-1",
        doc_id="doc-1",
        status=status,
        stage="parse",
        progress=25,
        updated_at=datetime.now(UTC),
    )


def _app(job: Job) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        settings=SimpleNamespace(sse_heartbeat_s=15.0),
    )
    app.include_router(router)
    register_exception_handlers(app)
    return app


def test_get_job_serializes_camel_case() -> None:
    app = _app(_job())
    app.dependency_overrides[get_get_job_use_case] = lambda: FakeGetJob(_job())

    with TestClient(app) as client:
        response = client.get("/jobs/job-1")

    assert response.status_code == 200
    body = response.json()
    assert body["jobId"] == "job-1"
    assert body["docId"] == "doc-1"
    assert body["status"] == "PROCESSING"


def test_get_missing_job_returns_404() -> None:
    app = _app(_job())
    app.dependency_overrides[get_get_job_use_case] = lambda: FakeGetJob(_job())

    with TestClient(app) as client:
        response = client.get("/jobs/other")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_sse_sends_current_state_and_updates() -> None:
    initial = _job("PROCESSING")
    completed = _job("COMPLETED")
    app = _app(initial)
    stream = FakeStreamJobs([initial, completed])
    app.dependency_overrides[get_stream_job_events_use_case] = lambda: stream

    with TestClient(app) as client:
        response = client.get("/jobs/job-1/events")

    assert response.status_code == 200
    assert "event: job" in response.text
    assert '"jobId":"job-1"' in response.text
    assert '"status":"PROCESSING"' in response.text
    assert '"status":"COMPLETED"' in response.text
