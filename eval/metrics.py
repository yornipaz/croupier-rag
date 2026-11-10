"""Pure metric helpers for the Croupier RAG evaluation harness.

This module deliberately depends only on the Python standard library so it can
be unit-tested without the API, network access or third-party packages.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

SUMMARY_METRICS: tuple[str, ...] = (
    "hitAtK",
    "figureHit",
    "refusalCorrect",
    "llmCallRate",
    "chunksRetrievedMean",
    "chunksSentMean",
    "chunksSentP95",
    "contextTokensMean",
    "contextTokensP95",
    "promptTokensMean",
    "promptTokensP95",
    "completionTokensMean",
    "latencyP50",
    "latencyP95",
)

RATE_METRICS = frozenset({"hitAtK", "figureHit", "refusalCorrect", "llmCallRate"})


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


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ratio(values: Sequence[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


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
    sources = response.get("sources") or []
    source_pages = [
        int(source["page"])
        for source in sources
        if isinstance(source, Mapping) and source.get("page") is not None
    ]
    images = response.get("images") or []
    sufficient = response.get("sufficient")
    sufficient_bool = bool(sufficient) if sufficient is not None else None

    if error is not None or response == {}:
        hit_at_k: bool | None = None if should_refuse else False
        figure_hit: bool | None = False if needs_figure else None
        refusal_correct = False
    else:
        hit_at_k = None if should_refuse else bool(set(expected_pages).intersection(source_pages))
        figure_hit = bool(images) if needs_figure else None
        refusal_correct = sufficient_bool is False if should_refuse else sufficient_bool is True

    usage = response.get("usage") or {}
    return {
        "id": str(case.get("id", "")),
        "question": str(case.get("question", "")),
        "expectedPages": expected_pages,
        "needsFigure": needs_figure,
        "shouldRefuse": should_refuse,
        "sufficient": sufficient_bool,
        "sourcePages": source_pages,
        "imageCount": len(images),
        "hitAtK": hit_at_k,
        "figureHit": figure_hit,
        "refusalCorrect": refusal_correct,
        "usage": {
            "chunksRetrieved": int(usage.get("chunksRetrieved") or 0),
            "chunksSent": int(usage.get("chunksSent") or 0),
            "contextTokens": int(usage.get("contextTokens") or 0),
            "promptTokens": int(usage.get("promptTokens") or 0),
            "completionTokens": int(usage.get("completionTokens") or 0),
            "latencyMs": int(usage.get("latencyMs") or 0),
            "llmCalled": bool(usage.get("llmCalled") or False),
        },
        "error": error,
    }


def summarize(results: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Aggregate per-question rows into the metrics shown by the harness."""
    ok = [row for row in results if not row.get("error")]
    answerable = [row for row in ok if not row.get("shouldRefuse")]
    figure_rows = [row for row in ok if row.get("needsFigure")]

    chunks_retrieved = [float(row["usage"]["chunksRetrieved"]) for row in ok]
    chunks_sent = [float(row["usage"]["chunksSent"]) for row in ok]
    context_tokens = [float(row["usage"]["contextTokens"]) for row in ok]
    prompt_tokens = [float(row["usage"]["promptTokens"]) for row in ok]
    completion_tokens = [float(row["usage"]["completionTokens"]) for row in ok]
    latencies = [float(row["usage"]["latencyMs"]) for row in ok]

    return {
        "questions": len(results),
        "errors": len(results) - len(ok),
        "hitAtK": _ratio([bool(row.get("hitAtK")) for row in answerable]),
        "figureHit": _ratio([bool(row.get("figureHit")) for row in figure_rows]),
        "refusalCorrect": _ratio([bool(row.get("refusalCorrect")) for row in ok]),
        "llmCallRate": _ratio([bool(row["usage"]["llmCalled"]) for row in ok]),
        "chunksRetrievedMean": _mean(chunks_retrieved),
        "chunksSentMean": _mean(chunks_sent),
        "chunksSentP95": percentile(chunks_sent, 95),
        "contextTokensMean": _mean(context_tokens),
        "contextTokensP95": percentile(context_tokens, 95),
        "promptTokensMean": _mean(prompt_tokens),
        "promptTokensP95": percentile(prompt_tokens, 95),
        "completionTokensMean": _mean(completion_tokens),
        "latencyP50": percentile(latencies, 50),
        "latencyP95": percentile(latencies, 95),
    }


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
