from __future__ import annotations

from typing import Protocol

from app.shared.chunks import BBox


class ImageUrlBuilderPort(Protocol):
    def build(self, document_id: str, page: int, bbox: BBox) -> str: ...
