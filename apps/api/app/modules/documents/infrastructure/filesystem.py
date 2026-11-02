from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from app.shared.chunks import BBox
from app.shared.errors import DocumentNotFoundError, UpstreamError
from app.shared.identifiers import require_safe_id


class FileSystemStorage:
    """PDF + rendered-image storage under DATA_DIR (implements both ports)."""

    def __init__(self, data_dir: Path) -> None:
        self._files_dir = data_dir / "files"
        self._images_dir = data_dir / "images"

    async def save_pdf(self, document_id: str, content: bytes) -> Path:
        path = self._pdf_path(document_id)
        try:
            await asyncio.to_thread(self._atomic_write, path, content)
        except OSError as exc:
            raise UpstreamError(
                "Could not persist the uploaded PDF",
                details={"errorType": type(exc).__name__},
            ) from exc
        return path

    async def pdf_path(self, document_id: str) -> Path:
        path = self._pdf_path(document_id)
        exists = await asyncio.to_thread(path.is_file)
        if not exists:
            raise DocumentNotFoundError(f"Document file not found: {document_id}")
        return path

    async def delete_document(self, document_id: str) -> None:
        try:
            await asyncio.to_thread(self._delete_sync, document_id)
        except OSError as exc:
            raise UpstreamError(
                "Could not delete document files",
                details={"errorType": type(exc).__name__},
            ) from exc

    async def save_image(
        self,
        document_id: str,
        image_id: str,
        content: bytes,
        *,
        page: int,
        bbox: BBox,
    ) -> Path:
        require_safe_id(document_id, kind="document id")
        require_safe_id(image_id, kind="image id")
        image_dir = self._images_dir / document_id
        path = image_dir / f"{image_id}.png"
        metadata = json.dumps(
            {
                "image_id": image_id,
                "document_id": document_id,
                "page": page,
                "bbox": list(bbox),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            await asyncio.to_thread(self._atomic_write, path, content)
            await asyncio.to_thread(
                self._atomic_write,
                image_dir / f"{image_id}.json",
                metadata,
            )
        except OSError as exc:
            raise UpstreamError(
                "Could not persist an extracted image",
                details={"errorType": type(exc).__name__},
            ) from exc
        return path

    def _pdf_path(self, document_id: str) -> Path:
        require_safe_id(document_id, kind="document id")
        return self._files_dir / f"{document_id}.pdf"

    def _delete_sync(self, document_id: str) -> None:
        self._pdf_path(document_id).unlink(missing_ok=True)
        shutil.rmtree(self._images_dir / document_id, ignore_errors=True)

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
