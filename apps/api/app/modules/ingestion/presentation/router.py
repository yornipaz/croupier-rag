from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from app.modules.ingestion.application.use_cases.get_job import GetJobUseCase
from app.modules.ingestion.application.use_cases.stream_job_events import StreamJobEventsUseCase
from app.modules.ingestion.presentation.schemas import JobSchema
from app.shared.jobs import Job

router = APIRouter(prefix="/jobs", tags=["ingestion"])


def get_get_job_use_case(request: Request) -> GetJobUseCase:
    use_case: GetJobUseCase = request.app.state.container.ingestion.get_job
    return use_case


def get_stream_job_events_use_case(request: Request) -> StreamJobEventsUseCase:
    use_case: StreamJobEventsUseCase = request.app.state.container.ingestion.stream_job_events
    return use_case


@router.get("/{job_id}", response_model=JobSchema)
async def get_job(
    job_id: str,
    use_case: Annotated[GetJobUseCase, Depends(get_get_job_use_case)],
) -> JobSchema:
    job = await use_case.execute(job_id)
    return JobSchema.from_job(job)


@router.get("/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    use_case: Annotated[StreamJobEventsUseCase, Depends(get_stream_job_events_use_case)],
) -> EventSourceResponse:
    current = await use_case.get_current(job_id)
    heartbeat = request.app.state.container.settings.sse_heartbeat_s

    async def source() -> AsyncIterator[ServerSentEvent]:
        yield _event(current)
        async for job in use_case.events(job_id):
            yield _event(job)

    return EventSourceResponse(
        source(),
        ping=heartbeat,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _event(job: Job) -> ServerSentEvent:
    schema = JobSchema.from_job(job)
    return ServerSentEvent(
        event="job",
        data=schema.model_dump_json(by_alias=True),
    )
