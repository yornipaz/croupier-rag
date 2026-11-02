from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingPort(Protocol):
    """Dense embedding port; dimension is required to size the Qdrant collection."""

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
