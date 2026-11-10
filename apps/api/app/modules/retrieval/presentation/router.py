from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.modules.retrieval.application.use_cases.retrieve_context import (
    RetrieveContextUseCase,
)
from app.modules.retrieval.presentation.schemas import (
    RetrievalRequest,
    RetrievalResponse,
)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_retrieve_context_use_case(request: Request) -> RetrieveContextUseCase:
    use_case: RetrieveContextUseCase = request.app.state.container.retrieval.retrieve_context
    return use_case


@router.post("/search", response_model=RetrievalResponse, response_model_exclude_none=True)
async def search(
    payload: RetrievalRequest,
    request: Request,
    use_case: Annotated[
        RetrieveContextUseCase,
        Depends(get_retrieve_context_use_case),
    ],
    debug: Annotated[bool, Query()] = False,
) -> RetrievalResponse:
    result = await use_case.execute(
        payload.query,
        payload.doc_id,
        payload.top_k,
        selection_mode=_selection_mode(request),
    )
    return RetrievalResponse.from_result(result, include_debug=debug)


def _selection_mode(request: Request) -> str | None:
    container = getattr(request.app.state, "container", None)
    settings = getattr(container, "settings", None)
    if settings is None or settings.env not in {"dev", "eval"}:
        return None
    mode = request.headers.get("X-Selection-Mode", "").strip().lower()
    return mode if mode in {"static", "dynamic"} else None
