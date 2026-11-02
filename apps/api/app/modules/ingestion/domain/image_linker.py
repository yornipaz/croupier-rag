from __future__ import annotations

import re
from dataclasses import replace

from app.modules.ingestion.domain.parsed import ParsedBlock, ParsedDocument, ParsedPage
from app.shared.chunks import BBox

CAPTION_RE = re.compile(
    r"^\s*(?:figura|fig\.?)\s*([0-9]+(?:[.\-][0-9]+)*)",
    re.IGNORECASE,
)
REFERENCE_RE = re.compile(
    r"\b(?:ver|v[eé]ase|vease|consultar|consulte)\s+(?:la\s+)?(?:figura|fig\.?)\s*"
    r"([0-9]+(?:[.\-][0-9]+)*)",
    re.IGNORECASE,
)


def link_images(
    document: ParsedDocument,
    *,
    fallback_max_gap_pt: float = 120.0,
) -> ParsedDocument:
    """Link captions, explicit references and nearby text to page images."""
    pages: list[ParsedPage] = []
    for page in document.pages:
        pages.append(_link_page(page, fallback_max_gap_pt=fallback_max_gap_pt))
    return replace(document, pages=tuple(pages))


def _link_page(page: ParsedPage, *, fallback_max_gap_pt: float) -> ParsedPage:
    blocks = list(page.blocks)
    images = [
        (index, block)
        for index, block in enumerate(blocks)
        if block.type == "image" and block.image_id
    ]
    if not images:
        return page

    captions: dict[int, tuple[str, str | None]] = {}
    figure_map: dict[str, str] = {}
    linked_images: set[str] = set()

    for index, block in enumerate(blocks):
        if block.type != "text":
            continue
        match = CAPTION_RE.match(block.text or "")
        if match is None:
            continue
        label = _normalize_label(match.group(1))
        image_id = _nearest_image_id(block.bbox, images)
        captions[index] = (label, image_id)
        if image_id is not None:
            figure_map.setdefault(label, image_id)
            linked_images.add(image_id)

    for index, block in enumerate(blocks):
        if index in captions or block.type not in ("text", "table"):
            continue
        references = [_normalize_label(label) for label in REFERENCE_RE.findall(block.text or "")]
        image_ids = tuple(
            dict.fromkeys(
                figure_map[label] for label in references if label in figure_map
            )
        )
        if image_ids:
            blocks[index] = replace(block, image_ids=image_ids)

    for index, (label, image_id) in captions.items():
        blocks[index] = replace(
            blocks[index],
            is_caption=True,
            caption_label=label,
            image_ids=(image_id,) if image_id is not None else (),
        )

    candidates = [
        (index, block)
        for index, block in enumerate(blocks)
        if block.type in ("text", "table") and index not in captions
    ]
    for _, image in images:
        image_id = image.image_id
        if image_id is None or image_id in linked_images:
            continue
        nearest = _nearest_block(image.bbox, candidates)
        if nearest is None:
            continue
        index, block = nearest
        gap = _vertical_gap(image.bbox, block.bbox)
        if gap > fallback_max_gap_pt:
            continue
        blocks[index] = replace(
            block,
            image_ids=tuple(dict.fromkeys((*block.image_ids, image_id))),
        )
        linked_images.add(image_id)

    return replace(page, blocks=tuple(blocks))


def _nearest_image_id(bbox: BBox, images: list[tuple[int, ParsedBlock]]) -> str | None:
    if not images:
        return None
    _, block = min(
        images,
        key=lambda item: (
            _vertical_gap(bbox, item[1].bbox),
            _horizontal_distance(bbox, item[1].bbox),
            item[0],
        ),
    )
    return block.image_id


def _nearest_block(
    bbox: BBox,
    candidates: list[tuple[int, ParsedBlock]],
) -> tuple[int, ParsedBlock] | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            _vertical_gap(bbox, item[1].bbox),
            _horizontal_distance(bbox, item[1].bbox),
            item[0],
        ),
    )


def _vertical_gap(first: BBox, second: BBox) -> float:
    if first[3] <= second[1]:
        return float(second[1] - first[3])
    if second[3] <= first[1]:
        return float(first[1] - second[3])
    return 0.0


def _horizontal_distance(first: BBox, second: BBox) -> float:
    first_center = (first[0] + first[2]) / 2.0
    second_center = (second[0] + second[2]) / 2.0
    return abs(first_center - second_center)


def _normalize_label(label: str) -> str:
    return label.strip().strip(".-").lower()
