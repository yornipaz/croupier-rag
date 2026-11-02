from __future__ import annotations

from app.modules.documents.application.dto.document import Document
from app.modules.documents.application.ports.document_repository import DocumentRepositoryPort


class ListDocumentsUseCase:
    def __init__(self, documents: DocumentRepositoryPort) -> None:
        self._documents = documents

    async def execute(self) -> list[Document]:
        return await self._documents.list_all()
