from __future__ import annotations

from typing import Protocol


class IngestionDispatcherPort(Protocol):
    async def enqueue(self, job_id: str, document_id: str) -> None: ...
