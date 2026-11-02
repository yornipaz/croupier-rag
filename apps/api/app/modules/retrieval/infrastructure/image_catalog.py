from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.modules.retrieval.application.dto.retrieval import ImageAsset
from app.shared.chunks import BBox
from app.shared.errors import UpstreamError
from app.shared.identifiers import require_safe_id
from app.shared.logging import get_logger

logger = get_logger(__name__)


class FileSystemImageCatalog:
    """Read image sidecars written by the parser next to each PNG."""

    def __init__(self, data_dir: Path) -> None:
        self._images_dir = data_dir / "images"

    async def get_many(
        self,
        document_id: str,
        image_ids: Sequence[str],
    ) -> dict[str, ImageAsset]:
        require_safe_id(document_id, kind="document id")
        if not image_ids:
            return {}
        values = await asyncio.gather(
            *(self._read(document_id, image_id) for image_id in image_ids)
        )
        return {asset.image_id: asset for asset in values if asset is not None}

    async def _read(self, document_id: str, image_id: str) -> ImageAsset | None:
        require_safe_id(image_id, kind="image id")
        path = self._images_dir / document_id / f"{image_id}.json"
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise UpstreamError(
                "Could not read image metadata",
                details={"errorType": type(exc).__name__},
            ) from exc
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
            page = int(payload["page"])
            bbox = _bbox(payload.get("bbox"))
            if bbox is None or page < 1:
                return None
            return ImageAsset(
                document_id=str(payload.get("document_id") or document_id),
                image_id=str(payload.get("image_id") or image_id),
                page=page,
                bbox=bbox,
            )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "retrieval.image_metadata_invalid",
                document_id=document_id,
                image_id=image_id,
            )
            return None


def _bbox(value: Any) -> BBox | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)
