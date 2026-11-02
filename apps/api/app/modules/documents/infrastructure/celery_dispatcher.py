from __future__ import annotations

import asyncio

from app.celery_app import INGESTION_TASK_NAME, celery_app
from app.shared.errors import UpstreamError


class CeleryIngestionDispatcher:
    async def enqueue(self, job_id: str, document_id: str) -> None:
        try:
            await asyncio.to_thread(
                celery_app.send_task,
                INGESTION_TASK_NAME,
                args=[job_id, document_id],
                task_id=job_id,
            )
        except Exception as exc:
            raise UpstreamError(
                "Could not enqueue the ingestion job",
                details={"errorType": type(exc).__name__},
            ) from exc
