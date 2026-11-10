#!/usr/bin/env python3
"""Diagnose section_path lengths and suspicious heading detection.

Reads the chunk payloads straight from Qdrant (no LLM, no re-ingestion) and
prints the distribution, the longest paths and the PDF blocks they point at.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from eval.metrics import percentile  # noqa: E402

from app.shared.tokens import count_tokens  # noqa: E402

DEFAULT_PDF = Path.home() / "Downloads" / "Manual de usuario app.pdf"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "manual_chunks"))
    parser.add_argument("--doc-id", default=os.getenv("DOC_ID"))
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(os.getenv("DEMO_PDF", str(DEFAULT_PDF))),
    )
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


def _candidate_bases(api_url: str) -> list[str]:
    base = api_url.rstrip("/")
    candidates = [base]
    prefix = os.getenv("API_PREFIX", "").strip().strip("/")
    if prefix:
        candidates.append(f"{base}/{prefix}")
    candidates.append(f"{base}/v1")
    return list(dict.fromkeys(candidates))


def _resolve_base(client: httpx.Client, api_url: str) -> str:
    for candidate in _candidate_bases(api_url):
        try:
            if client.get(f"{candidate}/health", timeout=5.0).status_code == 200:
                return candidate
        except httpx.HTTPError:
            continue
    raise SystemExit(f"No se encontró /health en {api_url}")


def _resolve_doc_id(client: httpx.Client, base: str, pdf: Path) -> str:
    response = client.get(f"{base}/documents")
    response.raise_for_status()
    for document in response.json():
        if document.get("filename") == pdf.name:
            return str(document["id"])
    raise SystemExit(f"No se encontró '{pdf.name}' en /documents. Usa --doc-id.")


def _scroll(
    client: httpx.Client, qdrant_url: str, collection: str, doc_id: str
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        body: dict[str, Any] = {
            "filter": {"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
            "limit": 100,
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            body["offset"] = offset
        response = client.post(
            f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll",
            json=body,
        )
        response.raise_for_status()
        result = response.json()["result"]
        batch = [point for point in result.get("points", []) if isinstance(point, dict)]
        points.extend(batch)
        offset = result.get("next_page_offset")
        if offset is None or not batch:
            return points


def _stats(values: Sequence[float]) -> str:
    return (
        f"min={min(values):.0f} p50={percentile(values, 50):.0f} "
        f"p90={percentile(values, 90):.0f} p95={percentile(values, 95):.0f} "
        f"max={max(values):.0f} mean={sum(values) / len(values):.0f}"
    )


def _suspicious_components(path: Sequence[str]) -> list[str]:
    suspicious: list[str] = []
    for component in path:
        text = component.strip()
        if len(text) >= 90 or (len(text) >= 50 and re.search(r"[.:;]\s", text)):
            suspicious.append(text)
    return suspicious


def _short(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def main() -> int:
    args = _parse_args()
    pdf = args.pdf.expanduser().resolve()
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        base = _resolve_base(client, args.api_url)
        doc_id = args.doc_id or _resolve_doc_id(client, base, pdf)
        points = _scroll(client, args.qdrant_url, args.collection, doc_id)

    rows: list[dict[str, Any]] = []
    for point in points:
        payload = point.get("payload") or {}
        section_path = [str(part) for part in payload.get("section_path") or []]
        path_text = " > ".join(section_path)
        rows.append(
            {
                "chunkId": str(payload.get("id") or point.get("id")),
                "page": int(payload.get("page") or 0),
                "bbox": payload.get("bbox"),
                "chars": len(path_text),
                "tokens": count_tokens(path_text),
                "sectionPath": section_path,
                "suspicious": _suspicious_components(section_path),
                "text": str(payload.get("text") or ""),
            }
        )

    if not rows:
        raise SystemExit(f"No hay chunks para doc_id={doc_id}")

    chars = [float(row["chars"]) for row in rows]
    tokens = [float(row["tokens"]) for row in rows]
    print(f"Documento: {doc_id} · chunks={len(rows)}\n")
    print("## Distribución de section_path\n")
    print(f"- Caracteres: {_stats(chars)}")
    print(f"- Tokens:     {_stats(tokens)}\n")

    top = sorted(rows, key=lambda row: row["chars"], reverse=True)[: args.top]
    print(f"## Top {len(top)} section_path más largos\n")
    print("| # | page | bbox | chars | tokens | section_path | chunk |")
    print("| ---: | ---: | --- | ---: | ---: | --- | --- |")
    for index, row in enumerate(top, start=1):
        bbox = ",".join(f"{float(value):.0f}" for value in row["bbox"] or [])
        print(
            f"| {index} | {row['page']} | {bbox} | {row['chars']} | {row['tokens']} | "
            f"{_short(' > '.join(row['sectionPath']), 220)} | {_short(row['text'], 90)} |"
        )

    suspicious = [row for row in rows if row["suspicious"]]
    print(f"\n## Posibles encabezados mal detectados: {len(suspicious)}/{len(rows)} chunks\n")
    if suspicious:
        print("| page | bbox | componente sospechoso |")
        print("| ---: | --- | --- |")
        for row in sorted(suspicious, key=lambda item: item["chars"], reverse=True)[:10]:
            bbox = ",".join(f"{float(value):.0f}" for value in row["bbox"] or [])
            print(f"| {row['page']} | {bbox} | {_short(row['suspicious'][0], 220)} |")

    if suspicious:
        print(
            "\nRegla implicada: `detect_sections` marcaba como encabezado cualquier bloque "
            "`text` no vacío cuyo tamaño de fuente redondeado estuviera en `heading_sizes` "
            "(>= talla del cuerpo × 1.15), sin comprobar longitud, líneas ni puntuación. "
            "La versión actual añade límites de longitud/palabras y descarta frases."
        )
    else:
        print(
            "\nNo se detectan encabezados sospechosos. La detección actual exige tamaño "
            "de fuente, longitud máxima, pocas líneas/palabras y descarta frases largas."
        )
    print(json.dumps({"document": doc_id, "chunks": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
