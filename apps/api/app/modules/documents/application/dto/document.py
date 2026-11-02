from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Document:
    """Persisted document metadata (the PDF bytes live in the file store)."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    sha256: str
    created_at: datetime
    job_id: str | None = None
    page_count: int | None = None
    chunk_count: int | None = None


@dataclass(frozen=True, slots=True)
class UploadedDocument:
    document_id: str
    job_id: str
