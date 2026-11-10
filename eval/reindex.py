#!/usr/bin/env python3
"""Delete and re-ingest DEMO_PDF through the API (required after chunking changes)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_PDF = Path.home() / "Downloads" / "Manual de usuario app.pdf"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(os.getenv("DEMO_PDF", str(DEFAULT_PDF))),
    )
    parser.add_argument("--job-timeout", type=float, default=900.0)
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


def _wait(client: httpx.Client, base: str, job_id: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        response = client.get(f"{base}/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        print(
            f"[reindex] {job['status']} {job.get('stage')} {job.get('progress')}%",
            file=sys.stderr,
        )
        if job["status"] == "COMPLETED":
            return
        if job["status"] == "FAILED":
            raise SystemExit(f"El job {job_id} falló: {job.get('error')}")
        if time.monotonic() >= deadline:
            raise SystemExit(f"Timeout esperando {job_id}")
        time.sleep(1.5)


def main() -> int:
    args = _parse_args()
    pdf = args.pdf.expanduser().resolve()
    if not pdf.exists():
        raise SystemExit(f"No existe el PDF: {pdf}")

    with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        base = _resolve_base(client, args.api_url)
        documents = client.get(f"{base}/documents")
        documents.raise_for_status()
        matching = [doc for doc in documents.json() if doc.get("filename") == pdf.name]
        for document in matching:
            print(f"[reindex] borrando {document['id']}", file=sys.stderr)
            response = client.delete(f"{base}/documents/{document['id']}")
            response.raise_for_status()

        with pdf.open("rb") as handle:
            response = client.post(
                f"{base}/documents",
                files={"file": (pdf.name, handle, "application/pdf")},
            )
        response.raise_for_status()
        uploaded = response.json()
        print(
            f"[reindex] job={uploaded['jobId']} document={uploaded['documentId']}",
            file=sys.stderr,
        )
        _wait(client, base, str(uploaded["jobId"]), args.job_timeout)
    print("Reindexación completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
