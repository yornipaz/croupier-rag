from __future__ import annotations

from app.modules.ingestion.domain.parsed import (
    ParsedBlock,
    ParsedDocument,
    ParsedPage,
)


def parsed_fixture(doc_id: str = "doc-1") -> ParsedDocument:
    return ParsedDocument(
        doc_id=doc_id,
        pages=(
            ParsedPage(
                number=1,
                width=612.0,
                height=792.0,
                blocks=(
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 40.0, 250.0, 70.0),
                        text="Manual de instalación",
                        font_size=20.0,
                        is_bold=True,
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 90.0, 500.0, 130.0),
                        text=(
                            "Antes de comenzar, revisa el panel de control mostrado "
                            "en la Figura 1."
                        ),
                        font_size=10.0,
                    ),
                    ParsedBlock(
                        type="image",
                        bbox=(50.0, 150.0, 260.0, 340.0),
                        image_id="img-1",
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 350.0, 330.0, 370.0),
                        text="Figura 1: panel de control principal.",
                        font_size=10.0,
                    ),
                    ParsedBlock(
                        type="text",
                        bbox=(50.0, 420.0, 500.0, 450.0),
                        text="La tabla siguiente resume los valores nominales.",
                        font_size=10.0,
                    ),
                    ParsedBlock(
                        type="table",
                        bbox=(50.0, 470.0, 400.0, 560.0),
                        text=(
                            "| Modelo | Voltaje |\n"
                            "| --- | --- |\n"
                            "| A-100 | 220 V |\n"
                            "| A-200 | 380 V |"
                        ),
                    ),
                ),
            ),
        ),
    )
