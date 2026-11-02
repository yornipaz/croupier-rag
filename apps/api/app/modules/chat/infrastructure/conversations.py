from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from redis.asyncio import Redis

from app.modules.chat.application.dto.chat import ChatRole, ChatTurn
from app.shared.errors import UpstreamError
from app.shared.identifiers import require_safe_id
from app.shared.logging import get_logger

logger = get_logger(__name__)


class RedisConversationRepository:
    def __init__(self, redis: Redis, *, prefix: str, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        self._redis = redis
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    async def get_recent(self, conversation_id: str, limit: int) -> list[ChatTurn]:
        require_safe_id(conversation_id, kind="conversation id")
        if limit < 1:
            return []
        try:
            raw_messages = await self._redis.lrange(self._key(conversation_id), -limit, -1)
        except Exception as exc:
            raise UpstreamError(
                "Could not read conversation history",
                details={"errorType": type(exc).__name__},
            ) from exc
        turns: list[ChatTurn] = []
        for raw in raw_messages:
            turn = _decode_turn(raw)
            if turn is not None:
                turns.append(turn)
        return turns

    async def append(
        self,
        conversation_id: str,
        turns: Sequence[ChatTurn],
        *,
        max_messages: int,
    ) -> None:
        require_safe_id(conversation_id, kind="conversation id")
        if not turns:
            return
        key = self._key(conversation_id)
        payloads = [
            json.dumps({"role": turn.role, "content": turn.content}, ensure_ascii=False)
            for turn in turns
        ]
        try:
            await self._redis.rpush(key, *payloads)
            await self._redis.ltrim(key, -max(1, max_messages), -1)
            await self._redis.expire(key, self._ttl_seconds)
        except Exception as exc:
            raise UpstreamError(
                "Could not persist conversation history",
                details={"errorType": type(exc).__name__},
            ) from exc

    def _key(self, conversation_id: str) -> str:
        return f"{self._prefix}{conversation_id}"


def _decode_turn(raw: str | bytes) -> ChatTurn | None:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("chat.conversation_message_skipped")
        return None
    if not isinstance(payload, dict):
        return None
    role = payload.get("role")
    content = payload.get("content")
    if role not in ("user", "assistant") or not isinstance(content, str):
        return None
    return ChatTurn(role=cast(ChatRole, role), content=content)
