from __future__ import annotations

from typing import Protocol

from app.modules.documents.application.dto.document import Document


class DocumentRepositoryPort(Protocol):
    async def save(self, document: Document) -> None: ...

    async def get(self, document_id: str) -> Document: ...

    async def list_all(self) -> list[Document]: ...

    async def delete(self, document_id: str) -> None: ...
