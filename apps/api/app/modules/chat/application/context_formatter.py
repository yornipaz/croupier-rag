from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from app.modules.retrieval.application.dto.retrieval import RetrievedChunk

SECTION_PROMPT_LEVELS = 2
SECTION_COMPONENT_MAX_CHARS = 60
FILENAME_MAX_CHARS = 36


class ContextFormatterPort(Protocol):
    def format(
        self,
        chunks: Sequence[RetrievedChunk],
        *,
        document_names: Mapping[str, str],
    ) -> str: ...


class VerboseContextFormatter:
    """Previous prompt format: repeated full metadata for every source."""

    def format(
        self,
        chunks: Sequence[RetrievedChunk],
        *,
        document_names: Mapping[str, str],
    ) -> str:
        _ = document_names
        if not chunks:
            return "(sin contexto recuperado)"
        blocks: list[str] = []
        for index, item in enumerate(chunks, start=1):
            chunk = item.chunk
            section = " > ".join(chunk.section_path) or "(sin sección)"
            blocks.append(
                f"[S{index}] archivo={chunk.doc_id} página={chunk.page} "
                f"sección={section} tipo={chunk.kind}\n{chunk.text}"
            )
        return "\n\n".join(blocks)


class CompactContextFormatter:
    """Short source legend plus compact ``[S#] text`` blocks."""

    def format(
        self,
        chunks: Sequence[RetrievedChunk],
        *,
        document_names: Mapping[str, str],
    ) -> str:
        if not chunks:
            return "(sin contexto recuperado)"
        legend = [
            _legend_line(index, item, document_names)
            for index, item in enumerate(chunks, start=1)
        ]
        blocks = [
            f"[S{index}] {item.chunk.text}"
            for index, item in enumerate(chunks, start=1)
        ]
        return "Fuentes: " + " · ".join(legend) + "\n\n" + "\n\n".join(blocks)


def _legend_line(
    index: int,
    item: RetrievedChunk,
    document_names: Mapping[str, str],
) -> str:
    chunk = item.chunk
    name = document_names.get(chunk.doc_id) or chunk.doc_id
    filename = _abbreviate_filename(name)
    section = _short_section(chunk.section_path)
    kind = "" if chunk.kind == "text" else f" ({chunk.kind})"
    section_part = f" §{section}" if section else ""
    return f"[S{index}] {filename} p.{chunk.page}{section_part}{kind}"


def _abbreviate_filename(name: str) -> str:
    filename = Path(name).name
    if len(filename) <= FILENAME_MAX_CHARS:
        return filename
    return filename[: FILENAME_MAX_CHARS - 1] + "…"


def _short_section(section_path: Sequence[str]) -> str:
    parts = [
        " ".join(part.split())[:SECTION_COMPONENT_MAX_CHARS]
        for part in section_path[-SECTION_PROMPT_LEVELS:]
        if part.strip()
    ]
    return " > ".join(parts)
