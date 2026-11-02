from __future__ import annotations

from app.modules.documents.application.ports.page_renderer import PageRendererPort
from app.shared.chunks import BBox
from app.shared.errors import BadRequestError


def parse_bbox(raw: str) -> BBox:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise BadRequestError("bbox must contain exactly four comma-separated numbers")
    try:
        x0, y0, x1, y1 = (float(part) for part in parts)
    except ValueError as exc:
        raise BadRequestError("bbox values must be numbers") from exc
    if x1 <= x0 or y1 <= y0:
        raise BadRequestError("bbox must satisfy x1 > x0 and y1 > y0")
    return (x0, y0, x1, y1)


class RenderPageCropUseCase:
    def __init__(self, pages: PageRendererPort) -> None:
        self._pages = pages

    async def execute(
        self,
        document_id: str,
        page_number: int,
        bbox: str,
        *,
        highlight: bool,
    ) -> bytes:
        if page_number < 1:
            raise BadRequestError("page number must be >= 1")
        return await self._pages.render_crop(
            document_id,
            page_number,
            parse_bbox(bbox),
            highlight=highlight,
        )
