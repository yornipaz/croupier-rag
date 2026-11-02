from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.modules.ingestion.domain.parsed import ParsedDocument


class DocumentParserPort(Protocol):
    async def parse(self, pdf_path: Path, document_id: str) -> ParsedDocument: ...
