from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ImageStoragePort(Protocol):
    async def save_image(self, document_id: str, image_id: str, content: bytes) -> Path: ...
