from __future__ import annotations

from dataclasses import replace

from app.modules.chat.application.context_formatter import (
    CompactContextFormatter,
    VerboseContextFormatter,
)
from app.shared.tokens import count_tokens
from tests.modules.chat.helpers import retrieval_result


def _with_long_sections() -> tuple[object, ...]:
    chunks = retrieval_result().chunks
    long_path = (
        "Manuales de Usuario",
        "I - Manual Aplicación de descarga de pedidos",
        "1.- Conexión VPN La aplicación necesita una conexión VPN para comunicarse "
        "con el servidor de Eroski de manera segura y funcionando correctamente",
    )
    return tuple(
        replace(item, chunk=replace(item.chunk, section_path=long_path))
        for item in chunks
    )


def test_compact_formatter_reduces_tokens_and_preserves_citations() -> None:
    chunks = _with_long_sections()
    names = {item.chunk.doc_id: "Manual de usuario app.pdf" for item in chunks}

    compact = CompactContextFormatter().format(chunks, document_names=names)
    verbose = VerboseContextFormatter().format(chunks, document_names=names)

    assert count_tokens(compact) < count_tokens(verbose)
    assert "[S1]" in compact
    assert "[S2]" in compact
    assert "Manual de usuario app.pdf" in compact
    assert "p.1" in compact
    assert "Manual" in compact


def test_compact_formatter_keeps_only_last_two_section_levels() -> None:
    chunks = retrieval_result().chunks
    names = {item.chunk.doc_id: "manual.pdf" for item in chunks}

    compact = CompactContextFormatter().format(chunks, document_names=names)

    assert "§Manual" in compact
    assert "§Guía" in compact
