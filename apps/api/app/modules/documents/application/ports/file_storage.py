from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileStoragePort(Protocol):
    async def save_pdf(self, document_id: str, content: bytes) -> Path: ...

    async def pdf_path(self, document_id: str) -> Path: ...

    async def delete_document(self, document_id: str) -> None: ...
