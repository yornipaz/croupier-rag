from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument
from app.modules.ingestion.domain.tokenizer import count_tokens
from app.shared.chunks import BBox, Chunk, ChunkKind

_NAMESPACE = uuid.NAMESPACE_URL


def union_bbox(blocks: Sequence[ParsedBlock]) -> BBox:
    if not blocks:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(block.bbox[0] for block in blocks),
        min(block.bbox[1] for block in blocks),
        max(block.bbox[2] for block in blocks),
        max(block.bbox[3] for block in blocks),
    )


class _ChunkFactory:
    def __init__(self, document_id: str) -> None:
        self._document_id = document_id
        self._ordinal = 0

    def make(
        self,
        *,
        page: int,
        bbox: BBox,
        section_path: tuple[str, ...],
        kind: ChunkKind,
        text: str,
        image_ids: Sequence[str] = (),
    ) -> Chunk:
        self._ordinal += 1
        normalized = text.strip()
        chunk_id = str(
            uuid.uuid5(
                _NAMESPACE,
                f"{self._document_id}:{page}:{kind}:{self._ordinal}:{normalized}",
            )
        )
        return Chunk(
            id=chunk_id,
            doc_id=self._document_id,
            page=page,
            bbox=bbox,
            section_path=section_path,
            kind=kind,
            text=normalized,
            image_ids=tuple(dict.fromkeys(image_ids)),
            token_count=count_tokens(normalized),
        )


class OversizeSplitter:
    """Split long text by paragraph/sentence/clause, never by raw characters."""

    def __init__(self, max_tokens: int, overlap_tokens: int = 0) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if overlap_tokens < 0:
            raise ValueError("overlap_tokens must be >= 0")
        self._max_tokens = max_tokens
        self._overlap_tokens = min(overlap_tokens, max_tokens - 1)

    def split(self, text: str) -> list[str]:
        units = self._units(text)
        if not units:
            return []
        return self._pack(units)

    def _units(self, text: str) -> list[str]:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", text)
            if paragraph.strip()
        ]
        units: list[str] = []
        for paragraph in paragraphs:
            if count_tokens(paragraph) <= self._max_tokens:
                units.append(paragraph)
                continue
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
                if sentence.strip()
            ]
            for sentence in sentences:
                if count_tokens(sentence) <= self._max_tokens:
                    units.append(sentence)
                    continue
                clauses = [
                    clause.strip()
                    for clause in re.split(r"(?<=[,;:])\s+", sentence)
                    if clause.strip()
                ]
                if len(clauses) > 1:
                    for clause in clauses:
                        if count_tokens(clause) <= self._max_tokens:
                            units.append(clause)
                        else:
                            units.extend(self._split_words(clause))
                else:
                    units.extend(self._split_words(sentence))
        return units

    def _split_words(self, text: str) -> list[str]:
        words = text.split()
        if len(words) <= 1:
            return [text] if text.strip() else []
        units: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for word in words:
            word_tokens = count_tokens(word)
            if current and current_tokens + word_tokens > self._max_tokens:
                units.append(" ".join(current))
                current = []
                current_tokens = 0
            current.append(word)
            current_tokens += word_tokens
        if current:
            units.append(" ".join(current))
        return units

    def _pack(self, units: list[str]) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for unit in units:
            unit_tokens = count_tokens(unit)
            if current and current_tokens + unit_tokens > self._max_tokens:
                chunks.append(self._join(current))
                tail = self._overlap_tail(current)
                tail_tokens = sum(count_tokens(item) for item in tail)
                if tail and tail_tokens + unit_tokens <= self._max_tokens:
                    current = tail
                    current_tokens = tail_tokens
                else:
                    current = []
                    current_tokens = 0
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            chunks.append(self._join(current))
        return chunks

    def _overlap_tail(self, units: list[str]) -> list[str]:
        if self._overlap_tokens <= 0:
            return []
        tail: list[str] = []
        total = 0
        for unit in reversed(units):
            unit_tokens = count_tokens(unit)
            if total + unit_tokens > self._overlap_tokens:
                break
            tail.insert(0, unit)
            total += unit_tokens
        return tail

    @staticmethod
    def _join(units: list[str]) -> str:
        return "\n\n".join(unit.strip() for unit in units if unit.strip()).strip()


class TableChunker:
    """Keep a table in one chunk when possible; otherwise split by rows."""

    def __init__(self, max_tokens: int, splitter: OversizeSplitter) -> None:
        self._max_tokens = max_tokens
        self._splitter = splitter

    def chunk(
        self,
        block: ParsedBlock,
        *,
        page: int,
        factory: _ChunkFactory,
    ) -> list[Chunk]:
        markdown = (block.text or "").strip()
        if not markdown:
            return []
        pieces = self._split_markdown(markdown)
        return [
            factory.make(
                page=page,
                bbox=block.bbox,
                section_path=block.section_path,
                kind="table",
                text=piece,
                image_ids=block.image_ids,
            )
            for piece in pieces
        ]

    def _split_markdown(self, markdown: str) -> list[str]:
        if count_tokens(markdown) <= self._max_tokens:
            return [markdown]
        lines = [line for line in markdown.splitlines() if line.strip()]
        if len(lines) < 3 or not lines[1].lstrip().startswith("|"):
            return self._splitter.split(markdown) or [markdown]

        header = lines[:2]
        rows = lines[2:]
        chunks: list[str] = []
        current: list[str] = []
        for row in rows:
            candidate = [*header, *current, row]
            if current and count_tokens("\n".join(candidate)) > self._max_tokens:
                chunks.append("\n".join(header + current))
                current = []
            current.append(row)
        if current:
            chunks.append("\n".join(header + current))
        return chunks or [markdown]


class LayoutChunker:
    """Layout-aware strategy: headings, tables, captions and text runs."""

    def __init__(
        self,
        max_tokens: int,
        overlap_tokens: int = 0,
        *,
        splitter: OversizeSplitter | None = None,
    ) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self._max_tokens = max_tokens
        self._splitter = splitter or OversizeSplitter(max_tokens, overlap_tokens)
        self._tables = TableChunker(max_tokens, self._splitter)

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        factory = _ChunkFactory(document.doc_id)
        chunks: list[Chunk] = []
        pending_headings: list[ParsedBlock] = []
        current: list[ParsedBlock] = []
        current_section: tuple[str, ...] = ()

        for page in document.pages:
            for block in page.blocks:
                if block.type == "image":
                    continue

                if block.is_heading:
                    if current:
                        chunks.extend(
                            self._flush(current, page.number, current_section, factory)
                        )
                        current = []
                    pending_headings = [block]
                    current_section = block.section_path
                    continue

                if block.is_caption:
                    if current:
                        chunks.extend(
                            self._flush(current, page.number, current_section, factory)
                        )
                        current = []
                    chunks.extend(self._caption_chunks(block, page.number, factory))
                    continue

                if block.type == "table":
                    if current:
                        chunks.extend(
                            self._flush(current, page.number, current_section, factory)
                        )
                        current = []
                    chunks.extend(
                        self._tables.chunk(block, page=page.number, factory=factory)
                    )
                    pending_headings = []
                    continue

                text = (block.text or "").strip()
                if not text:
                    continue
                if current and block.section_path != current_section:
                    chunks.extend(self._flush(current, page.number, current_section, factory))
                    current = []

                if not current:
                    current_section = block.section_path
                    current = list(pending_headings)
                    pending_headings = []
                    if current and self._text_tokens([*current, block]) > self._max_tokens:
                        current = []
                    if not current and count_tokens(text) > self._max_tokens:
                        chunks.extend(
                            self._split_text_block(block, page.number, factory)
                        )
                        continue
                    current.append(block)
                    continue

                candidate = [*current, block]
                if self._text_tokens(candidate) <= self._max_tokens:
                    current = candidate
                    continue
                chunks.extend(self._flush(current, page.number, current_section, factory))
                current = []
                if count_tokens(text) > self._max_tokens:
                    chunks.extend(self._split_text_block(block, page.number, factory))
                else:
                    current = [block]

            if current:
                chunks.extend(self._flush(current, page.number, current_section, factory))
                current = []

        return chunks

    def _flush(
        self,
        blocks: list[ParsedBlock],
        page: int,
        section_path: tuple[str, ...],
        factory: _ChunkFactory,
    ) -> list[Chunk]:
        text = "\n".join((block.text or "").strip() for block in blocks).strip()
        if not text:
            return []
        pieces = (
            [text]
            if count_tokens(text) <= self._max_tokens
            else self._splitter.split(text) or [text]
        )
        bbox = union_bbox(blocks)
        image_ids = tuple(
            image_id for block in blocks for image_id in block.image_ids
        )
        return [
            factory.make(
                page=page,
                bbox=bbox,
                section_path=section_path,
                kind="text",
                text=piece,
                image_ids=image_ids,
            )
            for piece in pieces
        ]

    def _split_text_block(
        self,
        block: ParsedBlock,
        page: int,
        factory: _ChunkFactory,
    ) -> list[Chunk]:
        text = (block.text or "").strip()
        if not text:
            return []
        pieces = self._splitter.split(text) or [text]
        return [
            factory.make(
                page=page,
                bbox=block.bbox,
                section_path=block.section_path,
                kind="text",
                text=piece,
                image_ids=block.image_ids,
            )
            for piece in pieces
        ]

    def _caption_chunks(
        self,
        block: ParsedBlock,
        page: int,
        factory: _ChunkFactory,
    ) -> list[Chunk]:
        text = (block.text or "").strip()
        if not text:
            return []
        pieces = (
            [text]
            if count_tokens(text) <= self._max_tokens
            else self._splitter.split(text) or [text]
        )
        return [
            factory.make(
                page=page,
                bbox=block.bbox,
                section_path=block.section_path,
                kind="caption",
                text=piece,
                image_ids=block.image_ids,
            )
            for piece in pieces
        ]

    @staticmethod
    def _text_tokens(blocks: Sequence[ParsedBlock]) -> int:
        return count_tokens("\n".join((block.text or "") for block in blocks))
