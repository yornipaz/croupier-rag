from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pymupdf

from app.modules.ingestion.application.ports.image_storage import ImageStoragePort
from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument, ParsedPage
from app.shared.chunks import BBox
from app.shared.errors import BadRequestError
from app.shared.logging import get_logger

logger = get_logger(__name__)

_NAMESPACE = uuid.NAMESPACE_URL


@dataclass(frozen=True, slots=True)
class _RenderedImage:
    image_id: str
    page: int
    bbox: BBox
    content: bytes


class PyMuPDFParser:
    """Extract text, tables and raster images from a PDF using PyMuPDF."""

    def __init__(
        self,
        images: ImageStoragePort,
        *,
        min_image_size_pt: float = 50.0,
        image_dpi: int = 150,
    ) -> None:
        if min_image_size_pt < 0:
            raise ValueError("min_image_size_pt must be >= 0")
        if image_dpi < 1:
            raise ValueError("image_dpi must be >= 1")
        self._images = images
        self._min_image_size_pt = min_image_size_pt
        self._image_dpi = image_dpi

    async def parse(self, pdf_path: Path, document_id: str) -> ParsedDocument:
        parsed, rendered = await asyncio.to_thread(
            self._parse_sync,
            pdf_path,
            document_id,
        )
        if rendered:
            await asyncio.gather(
                *(
                    self._images.save_image(
                        document_id,
                        image.image_id,
                        image.content,
                        page=image.page,
                        bbox=image.bbox,
                    )
                    for image in rendered
                )
            )
        return parsed

    def _parse_sync(
        self,
        pdf_path: Path,
        document_id: str,
    ) -> tuple[ParsedDocument, list[_RenderedImage]]:
        try:
            document = pymupdf.open(pdf_path)
        except Exception as exc:
            raise BadRequestError("The uploaded PDF is corrupted or unsupported") from exc

        pages: list[ParsedPage] = []
        rendered: list[_RenderedImage] = []
        with document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1
                table_blocks, table_rects = self._tables(page)
                image_blocks, image_files = self._images_for_page(
                    page,
                    document_id,
                    page_number,
                )
                text_blocks = self._text_blocks(page, table_rects)
                blocks = [*text_blocks, *table_blocks, *image_blocks]
                blocks.sort(key=_reading_order)
                pages.append(
                    ParsedPage(
                        number=page_number,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        blocks=tuple(blocks),
                    )
                )
                rendered.extend(image_files)
        return ParsedDocument(doc_id=document_id, pages=tuple(pages)), rendered

    def _tables(self, page: pymupdf.Page) -> tuple[list[ParsedBlock], list[pymupdf.Rect]]:
        blocks: list[ParsedBlock] = []
        rects: list[pymupdf.Rect] = []
        finder = page.find_tables()
        for table in finder.tables:
            bbox = _bbox(table.bbox)
            if bbox is None:
                continue
            markdown_value = table.to_markdown()
            markdown = markdown_value if isinstance(markdown_value, str) else ""
            if not markdown.strip():
                markdown = _rows_to_markdown(table.extract())
            if not markdown.strip():
                continue
            blocks.append(ParsedBlock(type="table", bbox=bbox, text=markdown))
            rects.append(pymupdf.Rect(bbox))
        return blocks, rects

    def _images_for_page(
        self,
        page: pymupdf.Page,
        document_id: str,
        page_number: int,
    ) -> tuple[list[ParsedBlock], list[_RenderedImage]]:
        blocks: list[ParsedBlock] = []
        rendered: list[_RenderedImage] = []
        infos = cast(list[dict[str, Any]], page.get_image_info(xrefs=True))
        for index, info in enumerate(infos):
            bbox = _bbox(info.get("bbox"))
            if bbox is None:
                continue
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            if width < self._min_image_size_pt or height < self._min_image_size_pt:
                continue
            digest = info.get("digest")
            digest_text = digest.hex() if isinstance(digest, bytes) else str(digest or "")
            image_id = str(
                uuid.uuid5(
                    _NAMESPACE,
                    f"{document_id}:{page_number}:{index}:{info.get('xref')}:{digest_text}",
                )
            )
            try:
                pixmap = page.get_pixmap(
                    clip=pymupdf.Rect(bbox),
                    dpi=self._image_dpi,
                    alpha=False,
                )
                content = pixmap.tobytes("png")
            except Exception:
                logger.warning(
                    "ingestion.image_render_failed",
                    page=page_number,
                    image_index=index,
                )
                continue
            blocks.append(ParsedBlock(type="image", bbox=bbox, image_id=image_id))
            rendered.append(
                _RenderedImage(
                    image_id=image_id,
                    page=page_number,
                    bbox=bbox,
                    content=content,
                )
            )
        return blocks, rendered

    def _text_blocks(
        self,
        page: pymupdf.Page,
        table_rects: list[pymupdf.Rect],
    ) -> list[ParsedBlock]:
        payload = cast(dict[str, Any], page.get_text("dict"))
        raw_blocks = payload.get("blocks", [])
        if not isinstance(raw_blocks, list):
            return []

        blocks: list[ParsedBlock] = []
        for raw in raw_blocks:
            if not isinstance(raw, dict) or int(raw.get("type", -1)) != 0:
                continue
            bbox = _bbox(raw.get("bbox"))
            if bbox is None or any(_inside_table(bbox, rect) for rect in table_rects):
                continue

            lines = raw.get("lines", [])
            if not isinstance(lines, list):
                continue
            line_texts: list[str] = []
            sizes: list[float] = []
            bold = False
            for line in lines:
                if not isinstance(line, dict):
                    continue
                spans = line.get("spans", [])
                if not isinstance(spans, list):
                    continue
                span_texts: list[str] = []
                for span in spans:
                    if not isinstance(span, dict):
                        continue
                    text = str(span.get("text", ""))
                    if text:
                        span_texts.append(text)
                    size = span.get("size")
                    if isinstance(size, (int, float)):
                        sizes.append(float(size))
                    if _span_is_bold(span):
                        bold = True
                if span_texts:
                    line_texts.append("".join(span_texts))
            text = "\n".join(line_texts).strip()
            if not text:
                continue
            blocks.append(
                ParsedBlock(
                    type="text",
                    bbox=bbox,
                    text=text,
                    font_size=max(sizes) if sizes else None,
                    is_bold=bold,
                )
            )
        return blocks


def _bbox(value: Any) -> BBox | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _inside_table(block: BBox, table: pymupdf.Rect) -> bool:
    rect = pymupdf.Rect(block)
    intersection = rect & table
    if intersection.get_area() <= 0:
        return False
    area = rect.get_area()
    return area > 0 and intersection.get_area() / area >= 0.5


def _span_is_bold(span: dict[str, Any]) -> bool:
    flags = span.get("flags", 0)
    if isinstance(flags, int) and flags & 16:
        return True
    return "bold" in str(span.get("font", "")).lower()


def _reading_order(block: ParsedBlock) -> tuple[float, float]:
    return (round(block.bbox[1], 1), round(block.bbox[0], 1))


def _rows_to_markdown(rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [list(row) + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    separator = ["---"] * width
    lines = [
        "| " + " | ".join(str(cell).replace("|", "\\|") for cell in header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend(
        "| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |"
        for row in normalized[1:]
    )
    return "\n".join(lines)
