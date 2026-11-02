from __future__ import annotations

from datetime import datetime

from app.modules.documents.application.dto.document import Document
from app.shared.schemas import CamelModel


class DocumentSchema(CamelModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    job_id: str | None = None
    page_count: int | None = None
    chunk_count: int | None = None

    @classmethod
    def from_document(cls, document: Document) -> DocumentSchema:
        return cls(
            id=document.id,
            filename=document.filename,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            created_at=document.created_at,
            job_id=document.job_id,
            page_count=document.page_count,
            chunk_count=document.chunk_count,
        )


class UploadDocumentResponse(CamelModel):
    job_id: str
    document_id: str
