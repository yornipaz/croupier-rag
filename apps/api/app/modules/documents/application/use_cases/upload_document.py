from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from app.modules.documents.application.dto.document import Document, UploadedDocument
from app.modules.documents.application.ports.document_repository import DocumentRepositoryPort
from app.modules.documents.application.ports.file_storage import FileStoragePort
from app.modules.documents.application.ports.ingestion_dispatcher import IngestionDispatcherPort
from app.modules.ingestion.application.ports.jobs import JobRepositoryPort
from app.shared.errors import (
    AppError,
    BadRequestError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    UpstreamError,
)
from app.shared.jobs import Job

_ALLOWED_CONTENT_TYPES = frozenset(
    {"application/pdf", "application/x-pdf", "application/octet-stream"}
)


class UploadDocumentUseCase:
    """Validate, persist and enqueue one PDF upload."""

    def __init__(
        self,
        documents: DocumentRepositoryPort,
        files: FileStoragePort,
        jobs: JobRepositoryPort,
        dispatcher: IngestionDispatcherPort,
        *,
        max_upload_bytes: int,
    ) -> None:
        if max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be >= 1")
        self._documents = documents
        self._files = files
        self._jobs = jobs
        self._dispatcher = dispatcher
        self._max_upload_bytes = max_upload_bytes

    async def execute(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> UploadedDocument:
        safe_filename = filename.strip() or "document.pdf"
        raw_type = content_type or "application/octet-stream"
        normalized_type = raw_type.split(";", 1)[0].strip().lower()

        if normalized_type and normalized_type not in _ALLOWED_CONTENT_TYPES:
            raise UnsupportedMediaTypeError("Only PDF files are accepted")
        if not content:
            raise BadRequestError("The uploaded file is empty")
        if len(content) > self._max_upload_bytes:
            raise PayloadTooLargeError(
                f"PDF exceeds the {self._max_upload_bytes} byte upload limit",
                details={"maxBytes": self._max_upload_bytes},
            )
        if not content.startswith(b"%PDF-"):
            raise UnsupportedMediaTypeError("File is not a valid PDF (missing %PDF- header)")

        document_id = str(uuid4())
        job_id = str(uuid4())
        now = datetime.now(UTC)
        path = await self._files.save_pdf(document_id, content)
        document = Document(
            id=document_id,
            filename=safe_filename,
            content_type="application/pdf",
            size_bytes=len(content),
            storage_path=str(path),
            sha256=hashlib.sha256(content).hexdigest(),
            created_at=now,
            job_id=job_id,
        )
        job = Job(
            job_id=job_id,
            doc_id=document_id,
            status="PENDING",
            stage="queued",
            progress=0,
            updated_at=now,
        )

        try:
            await self._documents.save(document)
            await self._jobs.save(job)
            await self._dispatcher.enqueue(job_id, document_id)
        except Exception as exc:
            failed_job = replace(
                job,
                status="FAILED",
                stage="enqueue",
                error="No se pudo encolar la ingesta del documento",
                updated_at=datetime.now(UTC),
            )
            await self._best_effort(lambda: self._jobs.save(failed_job))
            await self._best_effort(lambda: self._files.delete_document(document_id))
            await self._best_effort(lambda: self._documents.delete(document_id))
            if isinstance(exc, AppError):
                raise
            raise UpstreamError(
                "No se pudo encolar la ingesta del documento",
                details={"errorType": type(exc).__name__},
            ) from exc

        return UploadedDocument(document_id=document_id, job_id=job_id)

    async def _best_effort(self, operation: Callable[[], Awaitable[None]]) -> None:
        try:
            await operation()
        except Exception:
            return
