from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.shared.chunks import BBox


class ImageStoragePort(Protocol):
    async def save_image(
        self,
        document_id: str,
        image_id: str,
        content: bytes,
        *,
        page: int,
        bbox: BBox,
    ) -> Path: ...
