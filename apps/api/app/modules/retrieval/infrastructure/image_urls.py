from __future__ import annotations

from app.shared.chunks import BBox


class CropImageUrlBuilder:
    """Build a stable URL against the existing page-crop endpoint."""

    def __init__(self, api_prefix: str = "") -> None:
        self._prefix = api_prefix.rstrip("/")

    def build(self, document_id: str, page: int, bbox: BBox) -> str:
        coordinates = ",".join(f"{value:.2f}" for value in bbox)
        return (
            f"{self._prefix}/documents/{document_id}/pages/{page}/crop"
            f"?bbox={coordinates}&highlight=false"
        )
