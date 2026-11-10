from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace

from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument, ParsedPage

HEADING_MAX_CHARS = 80
HEADING_MAX_LINES = 2
HEADING_MAX_WORDS = 12
HEADING_ITALIC_MAX_CHARS = 60


def detect_sections(document: ParsedDocument) -> ParsedDocument:
    """Detect headings by relative font size and annotate every block.

    Candidates must also look like headings: short, few lines, few words and
    not a full sentence. This avoids promoting merged heading+paragraph blocks
    (or long emphasized body lines) to ``section_path`` components.
    """
    body_size = _body_font_size(document)
    if body_size <= 0:
        return document

    threshold = body_size * 1.15
    heading_sizes = sorted(
        {
            round(block.font_size, 1)
            for page in document.pages
            for block in page.blocks
            if block.font_size is not None and _is_heading_candidate(block, threshold=threshold)
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
            if (
                block.type == "text"
                and size in heading_sizes
                and _is_heading_candidate(block, threshold=threshold)
            ):
                text = _normalize_heading(block.text or "")
                level = heading_sizes.index(size) + 1
                stack = stack[: level - 1]
                if not stack or stack[-1] != text:
                    stack.append(text)
                blocks.append(
                    replace(
                        block,
                        text=text,
                        is_heading=True,
                        section_path=tuple(stack),
                    )
                )
                continue
            blocks.append(replace(block, section_path=tuple(stack)))
        pages.append(replace(page, blocks=tuple(blocks)))
    return replace(document, pages=tuple(pages))


def _is_heading_candidate(block: ParsedBlock, *, threshold: float) -> bool:
    if block.type != "text" or block.font_size is None:
        return False
    text = _normalize_heading(block.text or "")
    if not text or block.font_size < threshold:
        return False
    if len(text) > HEADING_MAX_CHARS:
        return False
    if len(text.splitlines()) > HEADING_MAX_LINES:
        return False
    if len(text.split()) > HEADING_MAX_WORDS:
        return False
    if block.is_italic and not block.is_bold and len(text) > HEADING_ITALIC_MAX_CHARS:
        return False
    return not _looks_like_sentence(text)


def _looks_like_sentence(text: str) -> bool:
    if text.endswith((".", "?", "!")) and len(text.split()) > 6:
        return True
    return bool(re.search(r"[.!?]\s+\S", text))


def _normalize_heading(text: str) -> str:
    return " ".join(text.split())


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
