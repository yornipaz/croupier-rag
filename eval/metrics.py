"""Pure metric helpers for the Croupier RAG evaluation harness.

This module deliberately depends only on the Python standard library so it can
be unit-tested without the API, network access or third-party packages.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

SUMMARY_METRICS: tuple[str, ...] = (
    "answerHit",
    "retrievalHit",
    "figureHit",
    "refusalCorrect",
    "llmCallRate",
    "chunksRetrievedMean",
    "chunksSentMean",
    "chunksSentP95",
    "systemTokensMean",
    "historyTokensMean",
    "contextTokensMean",
    "contextTokensP95",
    "questionTokensMean",
    "promptTemplateTokensMean",
    "promptEstimatedMean",
    "promptTokensMean",
    "promptTokensP95",
    "promptGapMean",
    "completionTokensMean",
    "denseCosineAnswerableP50",
    "denseCosineAnswerableP95",
    "denseCosineRefusalP50",
    "denseCosineRefusalP95",
    "denseCosineSeparationP50",
    "latencyP50",
    "latencyP95",
)

RATE_METRICS = frozenset(
    {"answerHit", "retrievalHit", "figureHit", "refusalCorrect", "llmCallRate"}
)


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (same convention as numpy's default)."""
    if not 0.0 <= p <= 100.0:
        raise ValueError("p must be between 0 and 100")
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ratio(values: Sequence[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _majority(values: Sequence[bool]) -> bool:
    return sum(1 for value in values if value) * 2 > len(values)


def _mode(values: Sequence[str]) -> str:
    return max(set(values), key=values.count) if values else ""


def _optional_median(values: Sequence[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return median(present) if present else None


def _page_list(items: Any) -> list[int]:
    pages: list[int] = []
    for item in items or []:
        if isinstance(item, Mapping) and item.get("page") is not None:
            pages.append(int(item["page"]))
    return pages


def _debug_pages(response: Mapping[str, Any], *, sent_only: bool) -> list[int]:
    debug = response.get("debug") or {}
    retrieved = debug.get("retrieved") or []
    return [
        int(hit["page"])
        for hit in retrieved
        if isinstance(hit, Mapping)
        and hit.get("page") is not None
        and (not sent_only or bool(hit.get("sent")))
    ]


def _top_dense_cosine(response: Mapping[str, Any]) -> float | None:
    debug = response.get("debug") or {}
    retrieved = debug.get("retrieved") or []
    values = [
        float(hit["denseCosine"])
        for hit in retrieved
        if isinstance(hit, Mapping) and hit.get("denseCosine") is not None
    ]
    return max(values) if values else None


def evaluate_question(
    case: Mapping[str, Any],
    response: Mapping[str, Any] | None,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one reproducible result row from a golden case and API response."""
    should_refuse = bool(case.get("should_refuse", False))
    needs_figure = bool(case.get("needs_figure", False))
    expected_pages = [int(page) for page in case.get("expected_pages", [])]

    response = response or {}
    source_pages = _page_list(response.get("sources"))
    retrieved_pages = _debug_pages(response, sent_only=False)
    sent_pages = _debug_pages(response, sent_only=True)
    images = response.get("images") or []
    sufficient = response.get("sufficient")
    sufficient_bool = bool(sufficient) if sufficient is not None else None

    if error is not None or response == {}:
        answer_hit: bool | None = None if should_refuse else False
        retrieval_hit: bool | None = None if should_refuse else False
        figure_hit: bool | None = False if needs_figure else None
        refusal_correct = False
    else:
        answer_hit = None if should_refuse else bool(set(expected_pages).intersection(source_pages))
        retrieval_hit = (
            None if should_refuse else bool(set(expected_pages).intersection(sent_pages))
        )
        figure_hit = bool(images) if needs_figure else None
        refusal_correct = sufficient_bool is False if should_refuse else sufficient_bool is True

    usage = response.get("usage") or {}
    prompt_tokens = int(usage.get("promptTokens") or 0)
    prompt_estimated = int(usage.get("promptEstimatedTokens") or 0)
    llm_called = bool(usage.get("llmCalled") or False)
    return {
        "id": str(case.get("id", "")),
        "question": str(case.get("question", "")),
        "split": str(case.get("split", "test")),
        "expectedPages": expected_pages,
        "needsFigure": needs_figure,
        "shouldRefuse": should_refuse,
        "sufficient": sufficient_bool,
        "sourcePages": source_pages,
        "retrievedPages": retrieved_pages,
        "sentPages": sent_pages,
        "answerHit": answer_hit,
        "retrievalHit": retrieval_hit,
        "figureHit": figure_hit,
        "refusalCorrect": refusal_correct,
        "topDenseCosine": _top_dense_cosine(response),
        "imageCount": len(images),
        "usage": {
            "chunksRetrieved": int(usage.get("chunksRetrieved") or 0),
            "chunksSent": int(usage.get("chunksSent") or 0),
            "systemTokens": int(usage.get("systemTokens") or 0),
            "historyTokens": int(usage.get("historyTokens") or 0),
            "contextTokens": int(usage.get("contextTokens") or 0),
            "questionTokens": int(usage.get("questionTokens") or 0),
            "promptTemplateTokens": int(usage.get("promptTemplateTokens") or 0),
            "promptEstimatedTokens": prompt_estimated,
            "promptTokens": prompt_tokens,
            "promptGapTokens": prompt_tokens - prompt_estimated if llm_called else 0,
            "completionTokens": int(usage.get("completionTokens") or 0),
            "promptSource": str(usage.get("promptSource") or "estimated"),
            "completionSource": str(usage.get("completionSource") or "estimated"),
            "breakdownSource": str(usage.get("breakdownSource") or "estimated"),
            "llmCalls": int(usage.get("llmCalls") or 0),
            "latencyMs": int(usage.get("latencyMs") or 0),
            "llmCalled": llm_called,
        },
        "error": error,
    }


def summarize(results: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Aggregate per-question rows into the metrics shown by the harness."""
    ok = [row for row in results if not row.get("error")]
    answerable = [row for row in ok if not row.get("shouldRefuse")]
    figure_rows = [row for row in ok if row.get("needsFigure")]
    refusal_rows = [row for row in ok if row.get("shouldRefuse")]

    chunks_retrieved = [float(row["usage"]["chunksRetrieved"]) for row in ok]
    chunks_sent = [float(row["usage"]["chunksSent"]) for row in ok]
    system_tokens = [float(row["usage"]["systemTokens"]) for row in ok]
    history_tokens = [float(row["usage"]["historyTokens"]) for row in ok]
    context_tokens = [float(row["usage"]["contextTokens"]) for row in ok]
    question_tokens = [float(row["usage"]["questionTokens"]) for row in ok]
    template_tokens = [float(row["usage"]["promptTemplateTokens"]) for row in ok]
    prompt_estimated = [float(row["usage"]["promptEstimatedTokens"]) for row in ok]
    prompt_tokens = [float(row["usage"]["promptTokens"]) for row in ok]
    prompt_gaps = [
        float(row["usage"]["promptGapTokens"]) for row in ok if row["usage"]["llmCalled"]
    ]
    completion_tokens = [float(row["usage"]["completionTokens"]) for row in ok]
    latencies = [float(row["usage"]["latencyMs"]) for row in ok]

    answerable_dense = [
        float(row["topDenseCosine"]) for row in answerable if row.get("topDenseCosine") is not None
    ]
    refusal_dense = [
        float(row["topDenseCosine"])
        for row in refusal_rows
        if row.get("topDenseCosine") is not None
    ]
    answerable_p50 = percentile(answerable_dense, 50)
    refusal_p50 = percentile(refusal_dense, 50)

    return {
        "questions": len(results),
        "errors": len(results) - len(ok),
        "answerHit": _ratio([bool(row.get("answerHit")) for row in answerable]),
        "retrievalHit": _ratio([bool(row.get("retrievalHit")) for row in answerable]),
        "figureHit": _ratio([bool(row.get("figureHit")) for row in figure_rows]),
        "refusalCorrect": _ratio([bool(row.get("refusalCorrect")) for row in ok]),
        "llmCallRate": _ratio([bool(row["usage"]["llmCalled"]) for row in ok]),
        "chunksRetrievedMean": _mean(chunks_retrieved),
        "chunksSentMean": _mean(chunks_sent),
        "chunksSentP95": percentile(chunks_sent, 95),
        "systemTokensMean": _mean(system_tokens),
        "historyTokensMean": _mean(history_tokens),
        "contextTokensMean": _mean(context_tokens),
        "contextTokensP95": percentile(context_tokens, 95),
        "questionTokensMean": _mean(question_tokens),
        "promptTemplateTokensMean": _mean(template_tokens),
        "promptEstimatedMean": _mean(prompt_estimated),
        "promptTokensMean": _mean(prompt_tokens),
        "promptTokensP95": percentile(prompt_tokens, 95),
        "promptGapMean": _mean(prompt_gaps),
        "completionTokensMean": _mean(completion_tokens),
        "denseCosineAnswerableP50": answerable_p50,
        "denseCosineAnswerableP95": percentile(answerable_dense, 95),
        "denseCosineRefusalP50": refusal_p50,
        "denseCosineRefusalP95": percentile(refusal_dense, 95),
        "denseCosineSeparationP50": answerable_p50 - refusal_p50,
        "latencyP50": percentile(latencies, 50),
        "latencyP95": percentile(latencies, 95),
    }


def median_metrics(runs: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Element-wise median of the metrics from repeated evaluation runs."""
    if not runs:
        return {}
    keys = list(runs[0].keys())
    result: dict[str, float] = {}
    for key in keys:
        values = [float(run[key]) for run in runs if key in run]
        result[key] = median(values)
    return result


def aggregate_question_runs(
    runs: Sequence[Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Aggregate per-question rows across runs using medians and majorities."""
    if not runs:
        return []
    length = min(len(run) for run in runs)
    aggregated: list[dict[str, Any]] = []
    for index in range(length):
        rows = [run[index] for run in runs]
        base = dict(rows[0])
        for key in ("answerHit", "retrievalHit", "figureHit", "refusalCorrect"):
            values = [row.get(key) for row in rows if row.get(key) is not None]
            base[key] = None if not values else _majority([bool(value) for value in values])
        sufficient_values = [
            row.get("sufficient") for row in rows if row.get("sufficient") is not None
        ]
        base["sufficient"] = (
            None
            if not sufficient_values
            else _majority([bool(value) for value in sufficient_values])
        )
        base["sourcePages"] = sorted({page for row in rows for page in row.get("sourcePages", [])})
        base["retrievedPages"] = sorted(
            {page for row in rows for page in row.get("retrievedPages", [])}
        )
        base["sentPages"] = sorted({page for row in rows for page in row.get("sentPages", [])})
        base["topDenseCosine"] = _optional_median([row.get("topDenseCosine") for row in rows])
        base["error"] = next((row["error"] for row in rows if row.get("error")), None)
        base["usage"] = _aggregate_usage([row["usage"] for row in rows])
        aggregated.append(base)
    return aggregated


def _aggregate_usage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in rows[0]:
        values = [row[key] for row in rows]
        if key in {"llmCalled"}:
            result[key] = _majority([bool(value) for value in values])
        elif key in {"promptSource", "completionSource", "breakdownSource"}:
            result[key] = _mode([str(value) for value in values])
        else:
            result[key] = round(median([float(value) for value in values]))
    return result


def percent_change(before: float, after: float) -> float | None:
    """Percentage variation; ``None`` when the baseline is zero."""
    if before == 0:
        return None if after != 0 else 0.0
    return (after - before) / before * 100.0


def compare_summaries(
    before: Mapping[str, float],
    after: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Return one comparable row per metric, preserving display order."""
    keys = [key for key in SUMMARY_METRICS if key in before or key in after]
    rows: list[dict[str, Any]] = []
    for key in keys:
        previous = float(before.get(key, 0.0))
        current = float(after.get(key, 0.0))
        rows.append(
            {
                "metric": key,
                "before": previous,
                "after": current,
                "changePct": percent_change(previous, current),
            }
        )
    return rows
