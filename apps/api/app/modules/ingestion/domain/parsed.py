from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.shared.chunks import BBox

BlockType = Literal["text", "table", "image"]


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    type: BlockType
    bbox: BBox
    text: str | None = None
    font_size: float | None = None
    is_bold: bool = False
    is_italic: bool = False
    image_id: str | None = None
    section_path: tuple[str, ...] = ()
    image_ids: tuple[str, ...] = ()
    is_heading: bool = False
    is_caption: bool = False
    caption_label: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedPage:
    number: int
    width: float
    height: float
    blocks: tuple[ParsedBlock, ...]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    doc_id: str
    pages: tuple[ParsedPage, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)
