from __future__ import annotations

from typing import Any, cast

import pytest

from app.modules.chat.application.dto.chat import ChatTurn
from app.modules.chat.infrastructure.conversations import RedisConversationRepository
from app.shared.errors import BadRequestError


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.expirations: list[tuple[str, int]] = []

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self.lists.get(key, [])
        return values[start:end] if end != -1 else values[start:]

    async def rpush(self, key: str, *values: str) -> int:
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    async def ltrim(self, key: str, start: int, end: int) -> None:
        values = self.lists.get(key, [])
        self.lists[key] = values[start:] if end == -1 else values[start : end + 1]

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations.append((key, seconds))


def _repo() -> tuple[FakeRedis, RedisConversationRepository]:
    fake = FakeRedis()
    return fake, RedisConversationRepository(
        cast(Any, fake),
        prefix="conv:",
        ttl_seconds=60,
    )


async def test_conversation_repository_appends_trims_and_reads() -> None:
    fake, repository = _repo()

    await repository.append(
        "conv-1",
        [
            ChatTurn(role="user", content="Hola"),
            ChatTurn(role="assistant", content="¿Qué necesitas?"),
            ChatTurn(role="user", content="Voltaje"),
        ],
        max_messages=2,
    )

    assert fake.lists["conv:conv-1"] == [
        '{"role": "assistant", "content": "¿Qué necesitas?"}',
        '{"role": "user", "content": "Voltaje"}',
    ]
    turns = await repository.get_recent("conv-1", 2)
    assert [turn.content for turn in turns] == ["¿Qué necesitas?", "Voltaje"]
    assert fake.expirations == [("conv:conv-1", 60)]


async def test_conversation_repository_rejects_unsafe_id() -> None:
    _, repository = _repo()

    with pytest.raises(BadRequestError):
        await repository.get_recent("../bad", 2)
