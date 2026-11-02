from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast

JobStatus = Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]
_JOB_STATUSES: frozenset[str] = frozenset({"PENDING", "PROCESSING", "COMPLETED", "FAILED"})


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Job:
    """Background ingestion job shared by the API, worker and SSE stream."""

    job_id: str
    doc_id: str
    status: JobStatus
    stage: str
    progress: int
    error: str | None = None
    updated_at: datetime = field(default_factory=_now)


def job_to_dict(job: Job) -> dict[str, Any]:
    payload = asdict(job)
    payload["updated_at"] = job.updated_at.isoformat()
    return payload


def job_from_dict(payload: dict[str, Any]) -> Job:
    status = str(payload.get("status", ""))
    if status not in _JOB_STATUSES:
        raise ValueError(f"invalid job status: {status!r}")
    updated_raw = payload.get("updated_at")
    updated_at = (
        datetime.fromisoformat(str(updated_raw))
        if updated_raw
        else _now()
    )
    return Job(
        job_id=str(payload["job_id"]),
        doc_id=str(payload["doc_id"]),
        status=cast(JobStatus, status),
        stage=str(payload.get("stage", "queued")),
        progress=int(payload.get("progress", 0)),
        error=str(payload["error"]) if payload.get("error") is not None else None,
        updated_at=updated_at,
    )


def job_to_json(job: Job) -> str:
    return json.dumps(job_to_dict(job), ensure_ascii=False, separators=(",", ":"))


def job_from_json(raw: str | bytes) -> Job:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("job payload must be an object")
    return job_from_dict(cast(dict[str, Any], payload))
