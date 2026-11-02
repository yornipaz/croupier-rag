from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument, ParsedPage


def detect_sections(document: ParsedDocument) -> ParsedDocument:
    """Detect headings by relative font size and annotate every block."""
    body_size = _body_font_size(document)
    if body_size <= 0:
        return document

    threshold = body_size * 1.15
    heading_sizes = sorted(
        {
            round(block.font_size, 1)
            for page in document.pages
            for block in page.blocks
            if block.type == "text"
            and block.font_size is not None
            and block.font_size >= threshold
            and (block.text or "").strip()
        },
        reverse=True,
    )
    if not heading_sizes:
        return document

    stack: list[str] = []
    pages: list[ParsedPage] = []
    for page in document.pages:
        blocks: list[ParsedBlock] = []
        for block in page.blocks:
            size = round(block.font_size, 1) if block.font_size is not None else None
            if block.type == "text" and size in heading_sizes and (block.text or "").strip():
                level = heading_sizes.index(size) + 1
                stack = stack[: level - 1]
                stack.append((block.text or "").strip())
                blocks.append(
                    replace(
                        block,
                        is_heading=True,
                        section_path=tuple(stack),
                    )
                )
                continue
            blocks.append(replace(block, section_path=tuple(stack)))
        pages.append(replace(page, blocks=tuple(blocks)))
    return replace(document, pages=tuple(pages))


def _body_font_size(document: ParsedDocument) -> float:
    weights: dict[float, int] = defaultdict(int)
    for page in document.pages:
        for block in page.blocks:
            if block.type != "text" or block.font_size is None:
                continue
            text = (block.text or "").strip()
            if not text:
                continue
            weights[round(block.font_size, 1)] += max(1, len(text))
    if not weights:
        return 0.0
    return max(weights.items(), key=lambda item: (item[1], -item[0]))[0]
