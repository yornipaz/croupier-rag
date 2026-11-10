#!/usr/bin/env python3
"""Calibrate the conservative gate and adaptive cutoff on the calibration split.

Writes ``DATA_DIR/calibration.json`` consumed by the API. It never looks at the
test split.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from eval.calibration import calibrate_cutoff, calibrate_gate  # noqa: E402

from app.config.settings import get_settings  # noqa: E402

DEFAULT_PDF = Path.home() / "Downloads" / "Manual de usuario app.pdf"


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
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.getenv("CALIBRATION_OUT", str(REPO_ROOT / "data" / "calibration.json"))),
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=float(os.getenv("GATE_SAFETY_MARGIN", "0.05")),
    )
    parser.add_argument("--min-k", type=int, default=int(os.getenv("MIN_K", "3")))
    parser.add_argument("--max-k", type=int, default=int(os.getenv("MAX_K", "6")))
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=int(os.getenv("CANDIDATE_POOL", "20")),
    )
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


def _case_signals(
    client: httpx.Client,
    base: str,
    case: Mapping[str, Any],
    doc_id: str,
    candidate_pool: int,
) -> dict[str, Any]:
    response = client.post(
        f"{base}/retrieval/search?debug=true",
        json={"query": case["question"], "docId": doc_id, "topK": candidate_pool},
    )
    response.raise_for_status()
    debug = response.json()["debug"]
    retrieved = [hit for hit in debug.get("retrieved") or [] if isinstance(hit, Mapping)]
    dense = [float(hit["denseCosine"]) for hit in retrieved if hit.get("denseCosine") is not None]
    top1 = max(dense) if dense else 0.0
    median = statistics.median(dense) if dense else 0.0
    return {
        "id": case["id"],
        "shouldRefuse": bool(case.get("should_refuse")),
        "expectedPages": [int(page) for page in case.get("expected_pages", [])],
        "denseTop1": top1,
        "denseSeparation": top1 - median,
        "lexicalCoverage": float(debug.get("lexicalCoverage") or 0.0),
        "pages": [int(hit["page"]) for hit in retrieved if hit.get("page") is not None],
        "denseScores": dense,
        "candidates": retrieved,
    }


def main() -> int:
    args = _parse_args()
    dataset: list[dict[str, Any]] = json.loads(args.golden.read_text(encoding="utf-8"))
    calibration = [case for case in dataset if case.get("split") == "calibration"]
    if not calibration:
        raise SystemExit("El dataset no tiene casos con split=calibration")
    pdf = args.pdf.expanduser().resolve()

    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        base = _resolve_base(client, args.api_url)
        doc_id = args.doc_id or _resolve_doc_id(client, base, pdf)
        for case in calibration:
            rows.append(_case_signals(client, base, case, doc_id, args.candidate_pool))

    signals, thresholds, caught = calibrate_gate(rows, args.margin)
    rel_ratio, gap_ratio = calibrate_cutoff(rows, min_k=args.min_k, max_k=args.max_k)
    settings = get_settings()
    payload = {
        "embeddingModel": settings.embedding_model,
        "thresholds": thresholds,
        "signalsUsed": list(signals),
        "margin": args.margin,
        "nCalibration": len(rows),
        "createdAt": datetime.now(UTC).isoformat(),
        "cutoff": {"relRatio": rel_ratio, "gapRatio": gap_ratio},
        "nAnswerable": sum(1 for row in rows if not row["shouldRefuse"]),
        "nRefusal": sum(1 for row in rows if row["shouldRefuse"]),
        "gateCaughtRefusals": caught,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Calibración escrita en {args.out}")
    print(f"Señales: {signals} · margen={args.margin}")
    print(f"Umbrales: {json.dumps(thresholds, ensure_ascii=False)}")
    print(f"Cutoff: relRatio={rel_ratio} gapRatio={gap_ratio}")
    print(f"Rechazos detectados en calibración: {caught}/{payload['nRefusal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
