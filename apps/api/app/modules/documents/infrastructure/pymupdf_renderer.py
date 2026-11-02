from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import cast

import pymupdf

from app.modules.documents.application.ports.file_storage import FileStoragePort
from app.shared.chunks import BBox
from app.shared.errors import BadRequestError, NotFoundError, UpstreamError

_HIGHLIGHT_RGB = (255, 235, 59)
_HIGHLIGHT_ALPHA = 0.28


class PageNotFoundError(NotFoundError):
    code = "document_page_not_found"


class PyMuPDFPageRenderer:
    """Render a PDF region to PNG, optionally with a translucent highlight."""

    def __init__(
        self,
        files: FileStoragePort,
        cache_dir: Path,
        *,
        margin_pt: float = 12.0,
        dpi: int = 150,
    ) -> None:
        if margin_pt < 0:
            raise ValueError("margin_pt must be >= 0")
        if dpi < 1:
            raise ValueError("dpi must be >= 1")
        self._files = files
        self._cache_dir = cache_dir
        self._margin_pt = margin_pt
        self._dpi = dpi

    async def render_crop(
        self,
        document_id: str,
        page_number: int,
        bbox: BBox,
        *,
        highlight: bool,
    ) -> bytes:
        pdf_path = await self._files.pdf_path(document_id)
        cache_path = self._cache_path(document_id, page_number, bbox, highlight)
        cached = await asyncio.to_thread(cache_path.is_file)
        if cached:
            return await asyncio.to_thread(cache_path.read_bytes)

        try:
            png = await asyncio.to_thread(
                self._render_sync,
                pdf_path,
                page_number,
                bbox,
                highlight,
            )
            await asyncio.to_thread(self._write_cache, cache_path, png)
        except (BadRequestError, NotFoundError):
            raise
        except Exception as exc:
            raise UpstreamError(
                "Could not render the requested PDF region",
                details={"errorType": type(exc).__name__},
            ) from exc
        return png

    async def invalidate(self, document_id: str) -> None:
        await asyncio.to_thread(
            shutil.rmtree,
            self._cache_dir / document_id,
            True,
        )

    def _cache_path(self, document_id: str, page_number: int, bbox: BBox, highlight: bool) -> Path:
        key = ":".join(f"{value:.3f}" for value in bbox)
        digest = hashlib.sha256(
            f"{page_number}:{key}:{int(highlight)}:{self._dpi}".encode()
        ).hexdigest()[:24]
        return self._cache_dir / document_id / f"p{page_number}-{digest}.png"

    def _render_sync(
        self,
        pdf_path: Path,
        page_number: int,
        bbox: BBox,
        highlight: bool,
    ) -> bytes:
        with pymupdf.open(pdf_path) as document:
            if page_number > document.page_count:
                raise PageNotFoundError(f"Page {page_number} does not exist")
            page = document.load_page(page_number - 1)
            clip = pymupdf.Rect(
                bbox[0] - self._margin_pt,
                bbox[1] - self._margin_pt,
                bbox[2] + self._margin_pt,
                bbox[3] + self._margin_pt,
            )
            clip = clip & page.rect
            if clip.is_empty or clip.width <= 0 or clip.height <= 0:
                raise BadRequestError("bbox does not intersect the requested page")

            pixmap = page.get_pixmap(clip=clip, dpi=self._dpi, alpha=False)
            if highlight:
                pixmap = self._highlight(pixmap, clip, bbox)
            return cast(bytes, pixmap.tobytes("png"))

    def _highlight(
        self,
        pixmap: pymupdf.Pixmap,
        clip: pymupdf.Rect,
        bbox: BBox,
    ) -> pymupdf.Pixmap:
        if pixmap.n < 3:
            return pixmap
        scale_x = pixmap.width / clip.width
        scale_y = pixmap.height / clip.height
        x0 = _clamp(round((bbox[0] - clip.x0) * scale_x), 0, pixmap.width)
        y0 = _clamp(round((bbox[1] - clip.y0) * scale_y), 0, pixmap.height)
        x1 = _clamp(round((bbox[2] - clip.x0) * scale_x), 0, pixmap.width)
        y1 = _clamp(round((bbox[3] - clip.y0) * scale_y), 0, pixmap.height)
        if x1 <= x0 or y1 <= y0:
            return pixmap

        samples = bytearray(pixmap.samples)
        stride = pixmap.stride
        channels = pixmap.n
        for row in range(y0, y1):
            row_start = row * stride
            for column in range(x0, x1):
                offset = row_start + column * channels
                for channel, target in enumerate(_HIGHLIGHT_RGB):
                    original = samples[offset + channel]
                    samples[offset + channel] = round(
                        original * (1.0 - _HIGHLIGHT_ALPHA) + target * _HIGHLIGHT_ALPHA
                    )
        return pymupdf.Pixmap(
            pixmap.colorspace,
            pixmap.width,
            pixmap.height,
            bytes(samples),
            pixmap.alpha,
        )

    @staticmethod
    def _write_cache(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))
