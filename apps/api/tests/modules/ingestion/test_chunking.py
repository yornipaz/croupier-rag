from __future__ import annotations

from app.modules.ingestion.domain.chunking import LayoutChunker, OversizeSplitter
from app.modules.ingestion.domain.image_linker import link_images
from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument, ParsedPage
from app.modules.ingestion.domain.structure import detect_sections
from app.modules.ingestion.domain.tokenizer import count_tokens
from tests.modules.ingestion.helpers import parsed_fixture


def test_detect_sections_rejects_long_blocks_that_merge_heading_and_body() -> None:
    document = ParsedDocument(
        doc_id="doc-1",
        pages=(
            ParsedPage(
                number=1,
                width=612.0,
                height=792.0,
                blocks=(
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 40.0, 250.0, 70.0),
                        text="1.- Conexión VPN",
                        font_size=18.0,
                        is_bold=True,
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 75.0, 500.0, 85.0),
                        text=(
                            "Texto normal del manual con la talla del cuerpo. "
                            "Este párrafo es suficientemente largo para fijar la talla "
                            "dominante del documento y evitar que un bloque de título "
                            "fusionado con su párrafo se convierta en la talla del cuerpo. "
                            "Repetimos texto neutro para que el peso sea claramente mayor."
                            " Añadimos una frase final adicional para asegurar que la "
                            "talla del cuerpo domine el cálculo de la talla base."
                        ),
                        font_size=10.0,
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 80.0, 500.0, 400.0),
                        text=(
                            "1.- Conexión VPN La aplicación necesita una conexión VPN "
                            "para comunicarse con el servidor de Eroski de manera segura. "
                            "Es importante asegurarse de que la conexión VPN está "
                            "correctamente configurada y funcionando antes de iniciar "
                            "la aplicación. Actualmente Eroski recomienda GlobalPortect."
                        ),
                        font_size=18.0,
                    ),
                ),
            ),
        ),
    )

    detected = detect_sections(document)
    blocks = detected.pages[0].blocks

    assert blocks[0].is_heading is True
    assert blocks[1].is_heading is False
    assert blocks[1].section_path == ("1.- Conexión VPN",)
    assert blocks[2].is_heading is False
    assert blocks[2].section_path == ("1.- Conexión VPN",)


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
