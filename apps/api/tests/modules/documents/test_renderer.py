from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.modules.documents.infrastructure.filesystem import FileSystemStorage
from app.modules.documents.infrastructure.pymupdf_renderer import (
    PageNotFoundError,
    PyMuPDFPageRenderer,
)


def _pdf_bytes() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=400, height=400)
    page.insert_text((50, 50), "Panel de control", fontsize=18)
    content = document.tobytes()
    document.close()
    return content


async def test_renderer_crops_highlights_and_caches(tmp_path: Path) -> None:
    storage = FileSystemStorage(tmp_path / "data")
    await storage.save_pdf("doc-1", _pdf_bytes())
    renderer = PyMuPDFPageRenderer(
        storage,
        tmp_path / "cache",
        margin_pt=12,
        dpi=100,
    )

    plain = await renderer.render_crop("doc-1", 1, (40, 30, 220, 80), highlight=False)
    highlighted = await renderer.render_crop("doc-1", 1, (40, 30, 220, 80), highlight=True)
    cached = await renderer.render_crop("doc-1", 1, (40, 30, 220, 80), highlight=True)

    assert plain.startswith(b"\x89PNG")
    assert highlighted.startswith(b"\x89PNG")
    assert highlighted == cached
    assert plain != highlighted

    await renderer.invalidate("doc-1")
    with pytest.raises(PageNotFoundError):
        await renderer.render_crop("doc-1", 9, (40, 30, 220, 80), highlight=False)
