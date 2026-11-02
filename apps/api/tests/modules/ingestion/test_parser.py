from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.modules.documents.infrastructure.filesystem import FileSystemStorage
from app.modules.ingestion.infrastructure.parser import PyMuPDFParser


def _make_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=500, height=700)
    page.insert_text((50, 60), "Manual de prueba", fontsize=20, fontname="hebo")
    page.insert_text(
        (50, 100),
        "Texto introductorio sobre el equipo y sus componentes.",
        fontsize=10,
        fontname="helv",
    )

    # Draw images before the table grid: PyMuPDF's table finder is sensitive
    # to content ordering when images and vector lines share a page.
    large = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 100), 0)
    large.clear_with(180)
    page.insert_image(pymupdf.Rect(50, 280, 200, 420), pixmap=large)

    x0, y0, x1, y1 = 50, 140, 400, 240
    for x in (x0, 225, x1):
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0), width=1)
    for y in (y0, 190, y1):
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0), width=1)
    page.insert_text((60, 170), "Modelo", fontsize=10)
    page.insert_text((235, 170), "Voltaje", fontsize=10)
    page.insert_text((60, 220), "A-100", fontsize=10)
    page.insert_text((235, 220), "220 V", fontsize=10)

    page.insert_text((50, 440), "Figura 1: panel del equipo.", fontsize=10)

    # A second page contains only a tiny image, which the parser must ignore.
    second = document.new_page(width=300, height=300)
    small = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    small.clear_with(220)
    second.insert_image(pymupdf.Rect(50, 50, 70, 70), pixmap=small)

    document.save(path)
    document.close()


async def test_parser_extracts_text_table_and_images(tmp_path: Path) -> None:
    pdf_path = tmp_path / "manual.pdf"
    _make_pdf(pdf_path)

    data_dir = tmp_path / "data"
    storage = FileSystemStorage(data_dir)
    parser = PyMuPDFParser(storage, min_image_size_pt=50, image_dpi=72)

    parsed = await parser.parse(pdf_path, "doc-1")

    assert parsed.page_count == 2
    blocks = parsed.pages[0].blocks
    text_blocks = [block for block in blocks if block.type == "text"]
    table_blocks = [block for block in blocks if block.type == "table"]
    image_blocks = [block for block in blocks if block.type == "image"]
    assert not [block for block in parsed.pages[1].blocks if block.type == "image"]

    assert text_blocks[0].text == "Manual de prueba"
    assert text_blocks[0].font_size == pytest.approx(20.0)
    assert text_blocks[0].is_bold is True
    assert text_blocks[0].bbox[1] < text_blocks[1].bbox[1]

    assert len(table_blocks) == 1
    assert table_blocks[0].text is not None
    assert table_blocks[0].text.startswith("|Modelo|")
    assert all("Modelo" not in (block.text or "") for block in text_blocks)

    assert len(image_blocks) == 1
    image_id = image_blocks[0].image_id
    assert image_id is not None
    image_path = data_dir / "images" / "doc-1" / f"{image_id}.png"
    assert image_path.exists()
    assert image_path.read_bytes().startswith(b"\x89PNG")
