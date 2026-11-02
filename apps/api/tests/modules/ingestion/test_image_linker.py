from __future__ import annotations

from app.modules.ingestion.domain.image_linker import link_images
from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument, ParsedPage


def _document() -> ParsedDocument:
    return ParsedDocument(
        doc_id="doc-1",
        pages=(
            ParsedPage(
                number=1,
                width=600.0,
                height=800.0,
                blocks=(
                    ParsedBlock(
                        type="image",
                        bbox=(50.0, 100.0, 200.0, 250.0),
                        image_id="img-1",
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 260.0, 300.0, 280.0),
                        text="Fig. 1: panel frontal.",
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 400.0, 300.0, 420.0),
                        text="Consulte la Figura 1 para más detalles.",
                    ),
                    ParsedBlock(
                        type="image",
                        bbox=(50.0, 500.0, 200.0, 650.0),
                        image_id="img-2",
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 660.0, 300.0, 680.0),
                        text="Diagrama de conexiones.",
                    ),
                ),
            ),
        ),
    )


def test_caption_references_and_fallback_are_linked() -> None:
    linked = link_images(_document())
    blocks = linked.pages[0].blocks

    caption = blocks[1]
    assert caption.is_caption is True
    assert caption.caption_label == "1"
    assert caption.image_ids == ("img-1",)

    reference = blocks[2]
    assert reference.image_ids == ("img-1",)

    fallback = blocks[4]
    assert fallback.image_ids == ("img-2",)
