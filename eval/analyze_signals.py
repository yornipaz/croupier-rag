#!/usr/bin/env python3
"""Inspect retrieval signals on the calibration split (no LLM calls).

For each calibration question it calls ``POST /retrieval/search?debug=true`` and
prints denseCosine top1, top1-median separation, lexicalCoverage and sparseScore
top1. It then looks for simple zero-false-rejection rules that separate
answerable questions from refusals.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PDF = Path.home() / "Downloads" / "Manual de usuario app.pdf"
SIGNALS = ("denseTop1", "denseSeparation", "lexicalCoverage", "sparseTop1")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--golden", type=Path, default=REPO_ROOT / "eval" / "golden.json")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(os.getenv("DEMO_PDF", str(DEFAULT_PDF))),
    )
    parser.add_argument("--doc-id", default=os.getenv("DOC_ID"))
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


def _signal_row(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    debug = response.get("debug") or {}
    retrieved = [hit for hit in debug.get("retrieved") or [] if isinstance(hit, Mapping)]
    dense = [float(hit["denseCosine"]) for hit in retrieved if hit.get("denseCosine") is not None]
    sparse = [float(hit["sparseScore"]) for hit in retrieved if hit.get("sparseScore") is not None]
    top1 = max(dense) if dense else 0.0
    pool_median = statistics.median(dense) if dense else 0.0
    top_hit = max(
        (hit for hit in retrieved if hit.get("denseCosine") is not None),
        key=lambda hit: float(hit["denseCosine"]),
        default={},
    )
    return {
        "id": str(case["id"]),
        "question": str(case["question"]),
        "category": "refusal" if case.get("should_refuse") else "answerable",
        "denseTop1": top1,
        "denseSeparation": top1 - pool_median,
        "lexicalCoverage": float(debug.get("lexicalCoverage") or 0.0),
        "sparseTop1": max(sparse) if sparse else 0.0,
        "topPage": top_hit.get("page"),
    }


def _best_rules(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    answerable = [row for row in rows if row["category"] == "answerable"]
    refusals = [row for row in rows if row["category"] == "refusal"]
    if not answerable or not refusals:
        return []

    results: list[dict[str, Any]] = []
    for size in range(1, len(SIGNALS) + 1):
        for subset in combinations(SIGNALS, size):
            thresholds = {
                signal: min(float(row[signal]) for row in answerable) for signal in subset
            }
            caught = [
                row
                for row in refusals
                if any(float(row[signal]) < thresholds[signal] for signal in subset)
            ]
            false_rejects = [
                row
                for row in answerable
                if any(float(row[signal]) < thresholds[signal] for signal in subset)
            ]
            results.append(
                {
                    "signals": subset,
                    "thresholds": thresholds,
                    "caught": len(caught),
                    "refusals": len(refusals),
                    "falseRejects": len(false_rejects),
                    "caughtIds": [row["id"] for row in caught],
                }
            )
    return results


def _format_rule(rule: Mapping[str, Any]) -> str:
    thresholds = ", ".join(f"{signal}≥{value:.3f}" for signal, value in rule["thresholds"].items())
    return f"{' ∨ '.join(rule['signals'])} ({thresholds})"


def _print_group(title: str, rows: Sequence[Mapping[str, Any]]) -> None:
    print(f"\n### {title} ({len(rows)})\n")
    print("| id | denseTop1 | sep top1−mediana | lexicalCoverage | sparseTop1 | top page |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        print(
            f"| {row['id']} | {row['denseTop1']:.3f} | {row['denseSeparation']:.3f} | "
            f"{row['lexicalCoverage']:.3f} | {row['sparseTop1']:.2f} | {row['topPage']} |"
        )


def main() -> int:
    args = _parse_args()
    dataset: list[dict[str, Any]] = json.loads(args.golden.read_text(encoding="utf-8"))
    calibration = [case for case in dataset if case.get("split") == "calibration"]
    if not calibration:
        raise SystemExit("El dataset no tiene casos con split=calibration")
    pdf = args.pdf.expanduser().resolve()

    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        base = _resolve_base(client, args.api_url)
        doc_id = args.doc_id or _resolve_doc_id(client, base, pdf)
        for case in calibration:
            payload = {"query": case["question"], "docId": doc_id}
            response = client.post(f"{base}/retrieval/search?debug=true", json=payload)
            response.raise_for_status()
            rows.append(_signal_row(case, response.json()))

    answerable = [row for row in rows if row["category"] == "answerable"]
    refusals = [row for row in rows if row["category"] == "refusal"]
    print(f"## Señales de calibración · documento {doc_id} · {len(rows)} preguntas\n")
    _print_group("Contestables", answerable)
    _print_group("Rechazo", refusals)

    rules = _best_rules(rows)
    if not rules:
        print("\nNo hay suficientes grupos para evaluar reglas.")
        return 0

    best = max(
        rules,
        key=lambda rule: (
            rule["caught"],
            -rule["falseRejects"],
            -len(rule["signals"]),
        ),
    )
    singles = [rule for rule in rules if len(rule["signals"]) == 1]
    print("\n### Reglas con cero falsos rechazos (umbral = mínimo de contestables)\n")
    print("| Regla | Rechazos detectados | Falsos rechazos |")
    print("| --- | ---: | ---: |")
    for rule in singles:
        print(
            f"| {_format_rule(rule)} | {rule['caught']}/{rule['refusals']} | "
            f"{rule['falseRejects']} |"
        )
    print(
        f"| **Mejor combinación:** {_format_rule(best)} | "
        f"**{best['caught']}/{best['refusals']}** | **{best['falseRejects']}** |"
    )
    print(
        f"\nLa mejor combinación se apoya en {len(answerable)} contestables y "
        f"{len(refusals)} rechazos de calibración. Detecta: "
        f"{', '.join(best['caughtIds']) or 'ninguno'}."
    )
    if best["caught"] == best["refusals"]:
        print("Separa completamente ambos grupos en calibración con esta regla simple.")
    else:
        print(
            "Ninguna combinación simple de estas señales separa completamente ambos "
            "grupos en calibración."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
