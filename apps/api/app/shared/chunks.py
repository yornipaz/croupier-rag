from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChunkKind = Literal["text", "table", "caption"]
BBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Chunk:
    """Contract shared by ingestion, vector store, retrieval and chat.

    Coordinates are PDF points with the origin at the top-left corner. The id
    must be a deterministic UUID5 so re-ingesting a document is idempotent.
    """

    id: str
    doc_id: str
    page: int
    bbox: BBox
    section_path: tuple[str, ...]
    kind: ChunkKind
    text: str
    image_ids: tuple[str, ...]
    token_count: int
