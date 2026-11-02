from __future__ import annotations

from app.modules.documents.application.ports.document_repository import DocumentRepositoryPort
from app.modules.documents.application.ports.file_storage import FileStoragePort
from app.modules.documents.application.ports.page_renderer import PageRendererPort
from app.modules.documents.application.ports.vector_deleter import VectorDeleterPort
from app.modules.ingestion.application.ports.jobs import JobRepositoryPort


class DeleteDocumentUseCase:
    """Remove vectors, PDF, images, cache and metadata for a document."""

    def __init__(
        self,
        documents: DocumentRepositoryPort,
        files: FileStoragePort,
        jobs: JobRepositoryPort,
        vectors: VectorDeleterPort,
        pages: PageRendererPort,
    ) -> None:
        self._documents = documents
        self._files = files
        self._jobs = jobs
        self._vectors = vectors
        self._pages = pages

    async def execute(self, document_id: str) -> None:
        document = await self._documents.get(document_id)

        # Vectors first: if Qdrant is down the document remains retryable.
        await self._vectors.delete_by_doc(document_id)
        await self._files.delete_document(document_id)
        await self._pages.invalidate(document_id)
        if document.job_id:
            await self._jobs.delete(document.job_id)
        await self._documents.delete(document_id)
