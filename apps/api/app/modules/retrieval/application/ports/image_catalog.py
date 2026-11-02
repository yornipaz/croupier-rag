from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.modules.retrieval.application.dto.retrieval import ImageAsset


class ImageCatalogPort(Protocol):
    async def get_many(
        self,
        document_id: str,
        image_ids: Sequence[str],
    ) -> dict[str, ImageAsset]: ...
