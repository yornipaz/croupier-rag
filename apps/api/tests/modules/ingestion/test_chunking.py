from __future__ import annotations

from app.modules.ingestion.domain.chunking import LayoutChunker, OversizeSplitter
from app.modules.ingestion.domain.image_linker import link_images
from app.modules.ingestion.domain.structure import detect_sections
from app.modules.ingestion.domain.tokenizer import count_tokens
from tests.modules.ingestion.helpers import parsed_fixture


def test_detect_sections_uses_relative_font_size() -> None:
    document = detect_sections(parsed_fixture())

    blocks = document.pages[0].blocks
    assert blocks[0].is_heading is True
    assert blocks[0].section_path == ("Manual de instalación",)
    assert blocks[1].section_path == ("Manual de instalación",)
    assert blocks[5].section_path == ("Manual de instalación",)


def test_layout_chunker_emits_text_table_and_caption_with_image() -> None:
    document = link_images(detect_sections(parsed_fixture()))
    chunks = LayoutChunker(80, 0).chunk(document)

    kinds = {chunk.kind for chunk in chunks}
    assert kinds == {"text", "table", "caption"}
    caption = next(chunk for chunk in chunks if chunk.kind == "caption")
    assert caption.image_ids == ("img-1",)
    assert caption.section_path == ("Manual de instalación",)
    table = next(chunk for chunk in chunks if chunk.kind == "table")
    assert table.text.startswith("| Modelo |")
    assert table.token_count == count_tokens(table.text)
    assert all(chunk.page == 1 for chunk in chunks)


def test_chunk_ids_are_deterministic() -> None:
    document = link_images(detect_sections(parsed_fixture()))

    first = LayoutChunker(80, 0).chunk(document)
    second = LayoutChunker(80, 0).chunk(document)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.text for chunk in first] == [chunk.text for chunk in second]


def test_oversize_splitter_respects_token_limit() -> None:
    text = (
        "Primera oración con varias palabras para el manual. "
        "Segunda oración que también necesita dividirse. "
        "Tercera oración con información adicional del equipo. "
        "Cuarta oración de cierre del procedimiento."
    )

    chunks = OversizeSplitter(10, 0).split(text)

    assert len(chunks) > 1
    assert all(count_tokens(chunk) <= 10 for chunk in chunks)
    assert "Primera" in chunks[0]
