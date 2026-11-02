from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.documents.application.dto.document import Document
from app.shared.errors import DocumentNotFoundError, UpstreamError
from app.shared.identifiers import require_safe_id
from app.shared.logging import get_logger

logger = get_logger(__name__)


class FileSystemDocumentRepository:
    """Small JSON metadata repository; no database is required for this exercise."""

    def __init__(self, data_dir: Path) -> None:
        self._documents_dir = data_dir / "documents"

    async def save(self, document: Document) -> None:
        path = self._path(document.id)
        payload = json.dumps(
            self._to_dict(document),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        try:
            await asyncio.to_thread(self._atomic_write, path, payload)
        except OSError as exc:
            raise UpstreamError(
                "Could not persist document metadata",
                details={"errorType": type(exc).__name__},
            ) from exc

    async def get(self, document_id: str) -> Document:
        path = self._path(document_id)
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except FileNotFoundError as exc:
            raise DocumentNotFoundError(f"Document not found: {document_id}") from exc
        except OSError as exc:
            raise UpstreamError(
                "Could not read document metadata",
                details={"errorType": type(exc).__name__},
            ) from exc
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("metadata must be an object")
            return self._from_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamError("Document metadata is corrupted") from exc

    async def list_all(self) -> list[Document]:
        try:
            paths = await asyncio.to_thread(self._list_paths)
        except OSError as exc:
            raise UpstreamError(
                "Could not list documents",
                details={"errorType": type(exc).__name__},
            ) from exc

        documents: list[Document] = []
        for path in paths:
            try:
                raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("metadata must be an object")
                documents.append(self._from_dict(payload))
            except (OSError, KeyError, TypeError, ValueError):
                logger.warning("documents.metadata_skipped", path=str(path))
        return sorted(documents, key=lambda item: item.created_at, reverse=True)

    async def delete(self, document_id: str) -> None:
        path = self._path(document_id)
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError as exc:
            raise UpstreamError(
                "Could not delete document metadata",
                details={"errorType": type(exc).__name__},
            ) from exc

    def _path(self, document_id: str) -> Path:
        require_safe_id(document_id, kind="document id")
        return self._documents_dir / f"{document_id}.json"

    def _list_paths(self) -> list[Path]:
        if not self._documents_dir.exists():
            return []
        return sorted(self._documents_dir.glob("*.json"))

    @staticmethod
    def _to_dict(document: Document) -> dict[str, Any]:
        return {
            "id": document.id,
            "filename": document.filename,
            "content_type": document.content_type,
            "size_bytes": document.size_bytes,
            "storage_path": document.storage_path,
            "sha256": document.sha256,
            "created_at": document.created_at.isoformat(),
            "job_id": document.job_id,
            "page_count": document.page_count,
            "chunk_count": document.chunk_count,
        }

    @staticmethod
    def _from_dict(payload: dict[str, Any]) -> Document:
        page_count = payload.get("page_count")
        chunk_count = payload.get("chunk_count")
        return Document(
            id=str(payload["id"]),
            filename=str(payload["filename"]),
            content_type=str(payload.get("content_type", "application/pdf")),
            size_bytes=int(payload["size_bytes"]),
            storage_path=str(payload["storage_path"]),
            sha256=str(payload.get("sha256", "")),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            job_id=str(payload["job_id"]) if payload.get("job_id") is not None else None,
            page_count=int(page_count) if page_count is not None else None,
            chunk_count=int(chunk_count) if chunk_count is not None else None,
        )

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
