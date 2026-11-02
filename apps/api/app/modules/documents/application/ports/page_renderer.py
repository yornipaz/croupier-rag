from __future__ import annotations

from typing import Protocol

from app.shared.chunks import BBox


class PageRendererPort(Protocol):
    async def render_crop(
        self,
        document_id: str,
        page_number: int,
        bbox: BBox,
        *,
        highlight: bool,
    ) -> bytes: ...

    async def invalidate(self, document_id: str) -> None: ...
