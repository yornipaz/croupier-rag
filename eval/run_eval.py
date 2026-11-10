#!/usr/bin/env python3
"""Reproducible end-to-end evaluation for the Croupier RAG API.

Only ``httpx`` and the standard library are required. The script:

1. Optionally uploads ``DEMO_PDF`` and waits for its ingestion job.
2. Asks the selected split through ``POST /chat/ask?debug=true`` several times.
3. Computes retrieval, figure, refusal, token and latency metrics.
4. Writes ``eval/results/<label>.json`` and prints markdown tables.

Examples:
    python eval/run_eval.py --label baseline-v2 --ensure-doc
    python eval/run_eval.py --compare eval/results/baseline-v2.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.metrics import (  # noqa: E402
    RATE_METRICS,
    aggregate_question_runs,
    compare_summaries,
    evaluate_question,
    median_metrics,
    summarize,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_PDF = Path.home() / "Downloads" / "Manual de usuario app.pdf"

METRIC_LABELS = {
    "answerHit": "answer_hit (fuentes citadas)",
    "retrievalHit": "retrieval_hit (recuperado enviado)",
    "figureHit": "figure_hit (preguntas con figura)",
    "refusalCorrect": "refusal_correct (todas)",
    "llmCallRate": "tasa de llamadas al LLM",
    "chunksRetrievedMean": "chunksRetrieved medio",
    "chunksSentMean": "chunksSent medio",
    "chunksSentP95": "chunksSent p95",
    "systemTokensMean": "systemTokens medio",
    "historyTokensMean": "historyTokens medio",
    "contextTokensMean": "contextTokens medio",
    "contextTokensP95": "contextTokens p95",
    "questionTokensMean": "questionTokens medio",
    "promptTemplateTokensMean": "promptTemplateTokens medio",
    "promptEstimatedMean": "promptEstimatedTokens medio",
    "promptTokensMean": "promptTokens medio",
    "promptTokensP95": "promptTokens p95",
    "promptGapMean": "gap prompt real - estimado",
    "completionTokensMean": "completionTokens medio",
    "denseCosineAnswerableP50": "denseCosine contestables p50",
    "denseCosineAnswerableP95": "denseCosine contestables p95",
    "denseCosineRefusalP50": "denseCosine rechazo p50",
    "denseCosineRefusalP95": "denseCosine rechazo p95",
    "denseCosineSeparationP50": "separación denseCosine p50",
    "latencyP50": "latencia p50",
    "latencyP95": "latencia p95",
}

JOB_TIMEOUT_S = 900.0
REQUEST_TIMEOUT_S = 180.0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="latest", help="Nombre del resultado (default: latest)")
    parser.add_argument(
        "--golden",
        type=Path,
        default=None,
        help="Dataset JSON (default: eval/golden.json o eval/golden.draft.json)",
    )
    parser.add_argument(
        "--ensure-doc",
        action="store_true",
        help="Sube DEMO_PDF si no está indexado y espera al job COMPLETED",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(os.getenv("DEMO_PDF", str(DEFAULT_PDF))),
        help="PDF de prueba (default: $DEMO_PDF)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="Compara el resultado de --label contra este JSON (no ejecuta preguntas)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Número de repeticiones; el reporte usa la mediana (default: 3)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperatura enviada en la evaluación (default: 0)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Usa todos los splits; por defecto solo el split test",
    )
    parser.add_argument(
        "--selection-mode",
        choices=("static", "dynamic"),
        default=None,
        help="Header X-Selection-Mode (solo se aplica con ENV=dev|eval)",
    )
    parser.add_argument(
        "--job-timeout",
        type=float,
        default=JOB_TIMEOUT_S,
        help="Segundos máximos de espera del job de ingesta",
    )
    return parser.parse_args(argv)


def _resolve_golden(path: Path | None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    renamed = REPO_ROOT / "eval" / "golden.json"
    if renamed.exists():
        return renamed
    return REPO_ROOT / "eval" / "golden.draft.json"


def _validate_label(label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", label):
        raise SystemExit("--label solo admite letras, números, punto, guion y guion bajo")
    return label


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
            response = client.get(f"{candidate}/health", timeout=5.0)
        except httpx.HTTPError:
            continue
        if response.status_code == 200:
            return candidate
    raise SystemExit(f"No se encontró /health en {api_url} (probé prefijos '' , API_PREFIX y /v1)")


def _list_documents(client: httpx.Client, base: str) -> list[dict[str, Any]]:
    response = client.get(f"{base}/documents")
    response.raise_for_status()
    payload = response.json()
    return [item for item in payload if isinstance(item, dict)]


def _find_document(
    documents: Sequence[Mapping[str, Any]],
    filename: str,
) -> dict[str, Any] | None:
    for document in documents:
        if document.get("filename") == filename:
            return dict(document)
    return None


def _is_indexed(document: Mapping[str, Any]) -> bool:
    chunk_count = document.get("chunkCount")
    return isinstance(chunk_count, int) and chunk_count > 0


def _wait_for_job(
    client: httpx.Client,
    base: str,
    job_id: str,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_state = ""
    while True:
        response = client.get(f"{base}/jobs/{job_id}")
        response.raise_for_status()
        job: dict[str, Any] = response.json()
        state = f"{job.get('status')} {job.get('stage')} {job.get('progress')}%"
        if state != last_state:
            print(f"[ingesta] job {job_id}: {state}", file=sys.stderr)
            last_state = state
        status = job.get("status")
        if status == "COMPLETED":
            return job
        if status == "FAILED":
            raise SystemExit(f"El job {job_id} falló: {job.get('error')}")
        if time.monotonic() >= deadline:
            raise SystemExit(f"Timeout esperando el job {job_id} ({timeout_s:.0f}s)")
        time.sleep(1.5)


def _get_document(client: httpx.Client, base: str, document_id: str) -> dict[str, Any]:
    response = client.get(f"{base}/documents/{document_id}")
    response.raise_for_status()
    document: dict[str, Any] = response.json()
    return document


def _upload(
    client: httpx.Client,
    base: str,
    pdf: Path,
    timeout_s: float,
) -> dict[str, Any]:
    with pdf.open("rb") as handle:
        files = {"file": (pdf.name, handle, "application/pdf")}
        response = client.post(
            f"{base}/documents",
            files=files,
            timeout=max(timeout_s, 300.0),
        )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _ensure_document(
    client: httpx.Client,
    base: str,
    pdf: Path,
    *,
    ensure: bool,
    timeout_s: float,
) -> dict[str, Any]:
    filename = pdf.name
    document = _find_document(_list_documents(client, base), filename)
    if document is not None and _is_indexed(document):
        print(f"[ingesta] documento ya indexado: {document['id']}", file=sys.stderr)
        return document

    if document is not None and document.get("jobId"):
        _wait_for_job(client, base, str(document["jobId"]), timeout_s)
        return _get_document(client, base, str(document["id"]))

    if not ensure:
        raise SystemExit(f"'{filename}' no está indexado. Repite con --ensure-doc para subirlo.")

    print(f"[ingesta] subiendo {pdf}", file=sys.stderr)
    uploaded = _upload(client, base, pdf, timeout_s)
    job_id = str(uploaded["jobId"])
    document_id = str(uploaded["documentId"])
    _wait_for_job(client, base, job_id, timeout_s)
    return _get_document(client, base, document_id)


def _ask(
    client: httpx.Client,
    base: str,
    question: str,
    doc_id: str | None,
    *,
    temperature: float,
    selection_mode: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": question, "temperature": temperature}
    if doc_id:
        payload["docId"] = doc_id
    headers = {"X-Selection-Mode": selection_mode} if selection_mode else None
    response = client.post(f"{base}/chat/ask?debug=true", json=payload, headers=headers)
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def _format_metric(metric: str, value: float) -> str:
    if metric in RATE_METRICS:
        return f"{value * 100:.1f}%"
    if metric in {"latencyP50", "latencyP95"}:
        return f"{value:.0f} ms"
    if metric.startswith("denseCosine"):
        return f"{value:.3f}"
    return f"{value:.1f}"


def _format_change(change: float | None) -> str:
    return "n/a" if change is None else f"{change:+.1f}%"


def _render_summary(metrics: Mapping[str, float]) -> str:
    lines = [
        "| Métrica | Valor |",
        "| --- | ---: |",
    ]
    for metric, label in METRIC_LABELS.items():
        lines.append(f"| {label} | {_format_metric(metric, float(metrics.get(metric, 0.0)))} |")
    return "\n".join(lines)


def _render_runs(runs: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "| run | answer_hit | retrieval_hit | refusal | context tok | prompt tok | p50 ms |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in runs:
        metrics = run["metrics"]
        lines.append(
            f"| {run['run']} | {_format_metric('answerHit', metrics['answerHit'])} | "
            f"{_format_metric('retrievalHit', metrics['retrievalHit'])} | "
            f"{_format_metric('refusalCorrect', metrics['refusalCorrect'])} | "
            f"{metrics['contextTokensMean']:.1f} | {metrics['promptTokensMean']:.1f} | "
            f"{metrics['latencyP50']:.0f} |"
        )
    return "\n".join(lines)


def _render_questions(results: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "| id | split | esp | cit | env | ans | ret | fig | rech | ctx | gap | ms | LLM |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in results:
        expected = ",".join(str(page) for page in row["expectedPages"]) or "—"
        cited = ",".join(str(page) for page in row["sourcePages"]) or "—"
        sent = ",".join(str(page) for page in row["sentPages"]) or "—"
        answer = "—" if row["answerHit"] is None else ("sí" if row["answerHit"] else "no")
        retrieval = "—" if row["retrievalHit"] is None else ("sí" if row["retrievalHit"] else "no")
        figure = "—" if row["figureHit"] is None else ("sí" if row["figureHit"] else "no")
        refusal = "sí" if row["refusalCorrect"] else "no"
        usage = row["usage"]
        suffix = f" ⚠ {row['error']}" if row.get("error") else ""
        lines.append(
            f"| {row['id']}{suffix} | {row['split']} | {expected} | {cited} | {sent} | "
            f"{answer} | {retrieval} | {figure} | {refusal} | {usage['contextTokens']} | "
            f"{usage['promptGapTokens']} | {usage['latencyMs']} | "
            f"{'sí' if usage['llmCalled'] else 'no'} |"
        )
    return "\n".join(lines)


def _render_comparison(
    before: Mapping[str, float],
    after: Mapping[str, float],
    before_label: str,
    after_label: str,
) -> str:
    lines = [
        f"| Métrica | {before_label} | {after_label} | Variación |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in compare_summaries(before, after):
        metric = str(row["metric"])
        lines.append(
            f"| {METRIC_LABELS.get(metric, metric)} | "
            f"{_format_metric(metric, float(row['before']))} | "
            f"{_format_metric(metric, float(row['after']))} | "
            f"{_format_change(row['changePct'])} |"
        )
    return "\n".join(lines)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _write_result(label: str, payload: Mapping[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{label}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _run_compare(compare_path: Path, label: str) -> int:
    current_path = RESULTS_DIR / f"{label}.json"
    if not compare_path.exists():
        raise SystemExit(f"No existe el baseline: {compare_path}")
    if not current_path.exists():
        raise SystemExit(
            f"No existe {current_path}. Ejecuta antes `make eval` o "
            f"`python eval/run_eval.py --label {label}`."
        )
    before = json.loads(compare_path.read_text(encoding="utf-8"))
    after = json.loads(current_path.read_text(encoding="utf-8"))
    before_label = str(before.get("label") or compare_path.stem)
    after_label = str(after.get("label") or label)
    print(f"## Comparación: {before_label} → {after_label}\n")
    print(_render_comparison(before["metrics"], after["metrics"], before_label, after_label))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    label = _validate_label(str(args.label))

    if args.compare is not None:
        return _run_compare(args.compare.expanduser().resolve(), label)

    runs = int(args.runs)
    if runs < 1:
        raise SystemExit("--runs debe ser >= 1")
    if not 0.0 <= float(args.temperature) <= 2.0:
        raise SystemExit("--temperature debe estar entre 0 y 2")

    golden_path = _resolve_golden(args.golden)
    if not golden_path.exists():
        raise SystemExit(f"No existe el dataset: {golden_path}")
    pdf = args.pdf.expanduser().resolve()
    if not pdf.exists():
        raise SystemExit(f"No existe el PDF: {pdf} (define DEMO_PDF o usa --pdf)")

    dataset: list[dict[str, Any]] = json.loads(golden_path.read_text(encoding="utf-8"))
    if args.all:
        golden = dataset
    else:
        golden = [case for case in dataset if case.get("split", "test") == "test"]
    if not golden:
        raise SystemExit("El split seleccionado no contiene preguntas")
    api_url = os.getenv("API_URL", "http://localhost:8000")

    print(f"Dataset: {golden_path} ({len(golden)}/{len(dataset)} preguntas)")
    print(f"Split: {'all' if args.all else 'test'} · runs={runs} · temperature={args.temperature}")
    print(f"PDF: {pdf}")
    print(f"API: {api_url}")
    print()

    run_results: list[list[dict[str, Any]]] = []
    with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT_S, connect=10.0)) as client:
        base = _resolve_base(client, api_url)
        print(f"[ingesta] API base: {base}", file=sys.stderr)
        document = _ensure_document(
            client,
            base,
            pdf,
            ensure=bool(args.ensure_doc),
            timeout_s=float(args.job_timeout),
        )
        document_id = str(document["id"])
        print(
            f"[ingesta] documento {document_id} · páginas={document.get('pageCount')} "
            f"chunks={document.get('chunkCount')}",
            file=sys.stderr,
        )
        print()

        for run_index in range(1, runs + 1):
            print(f"=== Run {run_index}/{runs} ===", file=sys.stderr)
            results: list[dict[str, Any]] = []
            for index, case in enumerate(golden, start=1):
                question = str(case["question"])
                print(
                    f"[{index:02d}/{len(golden):02d}] {case['id']}: {question}",
                    file=sys.stderr,
                )
                try:
                    response = _ask(
                        client,
                        base,
                        question,
                        document_id,
                        temperature=float(args.temperature),
                        selection_mode=args.selection_mode,
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    results.append(evaluate_question(case, None, error=str(exc)))
                    print(f"  error: {exc}", file=sys.stderr)
                    continue
                results.append(evaluate_question(case, response))
            run_results.append(results)

    run_metrics = [summarize(results) for results in run_results]
    metrics = median_metrics(run_metrics)
    questions = aggregate_question_runs(run_results)
    payload = {
        "label": label,
        "generatedAt": datetime.now(UTC).isoformat(),
        "apiUrl": api_url,
        "config": {
            "runs": runs,
            "temperature": float(args.temperature),
            "split": "all" if args.all else "test",
            "selectionMode": args.selection_mode,
        },
        "document": {
            "id": document_id,
            "filename": document.get("filename"),
            "pageCount": document.get("pageCount"),
            "chunkCount": document.get("chunkCount"),
        },
        "golden": _display_path(golden_path),
        "metrics": metrics,
        "questions": questions,
        "runs": [
            {"run": index, "metrics": summary, "questions": results}
            for index, (summary, results) in enumerate(
                zip(run_metrics, run_results, strict=True),
                start=1,
            )
        ],
    }
    output_path = _write_result(label, payload)

    print(f"## Resultado `{label}` (mediana de {runs} corridas)\n")
    print(_render_summary(metrics))
    print()
    print("### Métricas por corrida\n")
    print(
        _render_runs(
            [
                {"run": index, "metrics": summary}
                for index, summary in enumerate(run_metrics, start=1)
            ]
        )
    )
    print()
    print("### Detalle por pregunta (mediana/mayoría)\n")
    print(_render_questions(questions))
    print()
    print(f"JSON: `{output_path}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
