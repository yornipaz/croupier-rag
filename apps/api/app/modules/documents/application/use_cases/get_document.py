from __future__ import annotations

from app.modules.documents.application.dto.document import Document
from app.modules.documents.application.ports.document_repository import DocumentRepositoryPort


class GetDocumentUseCase:
    def __init__(self, documents: DocumentRepositoryPort) -> None:
        self._documents = documents

    async def execute(self, document_id: str) -> Document:
        return await self._documents.get(document_id)
