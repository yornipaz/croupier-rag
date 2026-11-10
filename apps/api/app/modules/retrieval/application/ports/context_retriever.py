from __future__ import annotations

from typing import Protocol

from app.modules.retrieval.application.dto.retrieval import RetrievalResult


class ContextRetrieverPort(Protocol):
    async def execute(
        self,
        query: str,
        doc_id: str | None = None,
        top_k: int | None = None,
        *,
        selection_mode: str | None = None,
    ) -> RetrievalResult: ...
