from __future__ import annotations

from typing import Protocol


class VectorDeleterPort(Protocol):
    async def delete_by_doc(self, document_id: str) -> None: ...
