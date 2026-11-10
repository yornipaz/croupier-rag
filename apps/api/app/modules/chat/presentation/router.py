from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.modules.chat.application.use_cases.ask_question import AskQuestionUseCase
from app.modules.chat.presentation.schemas import (
    ChatAskRequest,
    ChatResponse,
    to_chat_turns,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def get_ask_question_use_case(request: Request) -> AskQuestionUseCase:
    use_case: AskQuestionUseCase = request.app.state.container.chat.ask
    return use_case


@router.post("/ask", response_model=ChatResponse, response_model_exclude_none=True)
async def ask(
    payload: ChatAskRequest,
    request: Request,
    use_case: Annotated[AskQuestionUseCase, Depends(get_ask_question_use_case)],
    debug: Annotated[bool, Query()] = False,
) -> ChatResponse:
    answer = await use_case.execute(
        payload.query,
        to_chat_turns(payload.history),
        payload.doc_id or None,
        conversation_id=payload.conversation_id or None,
        temperature=payload.temperature,
        selection_mode=_selection_mode(request),
    )
    return ChatResponse.from_answer(answer, include_debug=debug)


def _selection_mode(request: Request) -> str | None:
    container = getattr(request.app.state, "container", None)
    settings = getattr(container, "settings", None)
    if settings is None or settings.env not in {"dev", "eval"}:
        return None
    mode = request.headers.get("X-Selection-Mode", "").strip().lower()
    return mode if mode in {"static", "dynamic"} else None
