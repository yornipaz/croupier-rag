from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.modules.chat.application.dto.chat import ChatTurn


class ConversationRepositoryPort(Protocol):
    async def get_recent(self, conversation_id: str, limit: int) -> list[ChatTurn]: ...

    async def append(
        self,
        conversation_id: str,
        turns: Sequence[ChatTurn],
        *,
        max_messages: int,
    ) -> None: ...
