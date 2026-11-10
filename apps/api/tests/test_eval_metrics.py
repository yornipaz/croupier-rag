from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.metrics import (  # noqa: E402
    compare_summaries,
    evaluate_question,
    percent_change,
    percentile,
    summarize,
)

CASE_ANSWERABLE = {
    "id": "q1",
    "question": "¿Pregunta?",
    "expected_pages": [4, 5],
    "needs_figure": True,
    "should_refuse": False,
}

CASE_REFUSAL = {
    "id": "q2",
    "question": "¿Fuera del corpus?",
    "expected_pages": [],
    "needs_figure": False,
    "should_refuse": True,
}


def _response(
    *,
    sufficient: bool,
    source_pages: list[int],
    image_count: int = 0,
    usage: dict[str, int | bool] | None = None,
) -> dict[str, object]:
    return {
        "sufficient": sufficient,
        "sources": [{"page": page} for page in source_pages],
        "images": [{"url": f"image-{index}"} for index in range(image_count)],
        "usage": usage
        or {
            "chunksRetrieved": 3,
            "chunksSent": 2,
            "contextTokens": 100,
            "promptTokens": 130,
            "completionTokens": 20,
            "latencyMs": 500,
            "llmCalled": True,
        },
    }


def test_hit_at_k_matches_any_expected_page() -> None:
    row = evaluate_question(
        CASE_ANSWERABLE,
        _response(sufficient=True, source_pages=[9, 5], image_count=1),
    )

    assert row["hitAtK"] is True
    assert row["figureHit"] is True
    assert row["refusalCorrect"] is True
    assert row["sourcePages"] == [9, 5]

    miss = evaluate_question(
        CASE_ANSWERABLE,
        _response(sufficient=True, source_pages=[9], image_count=1),
    )
    assert miss["hitAtK"] is False


def test_figure_hit_requires_an_image_in_the_response() -> None:
    row = evaluate_question(
        CASE_ANSWERABLE,
        _response(sufficient=True, source_pages=[4], image_count=0),
    )

    assert row["figureHit"] is False


def test_refusal_correct_compares_should_refuse_with_sufficiency() -> None:
    correct = evaluate_question(
        CASE_REFUSAL,
        _response(sufficient=False, source_pages=[]),
    )
    wrong = evaluate_question(
        CASE_REFUSAL,
        _response(sufficient=True, source_pages=[3]),
    )

    assert correct["refusalCorrect"] is True
    assert correct["hitAtK"] is None
    assert correct["figureHit"] is None
    assert wrong["refusalCorrect"] is False


def test_summarize_computes_rates_means_and_percentiles() -> None:
    rows = [
        evaluate_question(
            CASE_ANSWERABLE,
            _response(
                sufficient=True,
                source_pages=[4],
                image_count=1,
                usage={
                    "chunksRetrieved": 3,
                    "chunksSent": 2,
                    "contextTokens": 10,
                    "promptTokens": 100,
                    "completionTokens": 10,
                    "latencyMs": 100,
                    "llmCalled": True,
                },
            ),
        ),
        evaluate_question(
            CASE_ANSWERABLE,
            _response(
                sufficient=True,
                source_pages=[9],
                image_count=0,
                usage={
                    "chunksRetrieved": 3,
                    "chunksSent": 4,
                    "contextTokens": 20,
                    "promptTokens": 200,
                    "completionTokens": 20,
                    "latencyMs": 200,
                    "llmCalled": True,
                },
            ),
        ),
        evaluate_question(
            CASE_REFUSAL,
            _response(
                sufficient=False,
                source_pages=[],
                usage={
                    "chunksRetrieved": 3,
                    "chunksSent": 0,
                    "contextTokens": 30,
                    "promptTokens": 0,
                    "completionTokens": 0,
                    "latencyMs": 300,
                    "llmCalled": False,
                },
            ),
        ),
    ]

    metrics = summarize(rows)

    assert metrics["questions"] == 3
    assert metrics["errors"] == 0
    assert metrics["hitAtK"] == pytest.approx(0.5)
    assert metrics["figureHit"] == pytest.approx(0.5)
    assert metrics["refusalCorrect"] == pytest.approx(1.0)
    assert metrics["llmCallRate"] == pytest.approx(2 / 3)
    assert metrics["contextTokensMean"] == pytest.approx(20.0)
    assert metrics["contextTokensP95"] == pytest.approx(29.0)
    assert metrics["promptTokensMean"] == pytest.approx(100.0)
    assert metrics["chunksSentMean"] == pytest.approx(2.0)
    assert metrics["chunksSentP95"] == pytest.approx(3.8)
    assert metrics["latencyP50"] == pytest.approx(200.0)
    assert metrics["latencyP95"] == pytest.approx(290.0)


def test_errored_questions_are_excluded_from_usage_metrics() -> None:
    ok = evaluate_question(CASE_ANSWERABLE, _response(sufficient=True, source_pages=[4]))
    failed = evaluate_question(CASE_ANSWERABLE, None, error="timeout")

    metrics = summarize([ok, failed])

    assert metrics["questions"] == 2
    assert metrics["errors"] == 1
    assert metrics["contextTokensMean"] == pytest.approx(100.0)
    assert failed["refusalCorrect"] is False


def test_percentile_uses_linear_interpolation() -> None:
    assert percentile([10, 20, 30, 40], 50) == pytest.approx(25.0)
    assert percentile([10, 20, 30, 40], 95) == pytest.approx(38.5)
    assert percentile([], 95) == 0.0
    assert percentile([7], 50) == 7.0


def test_compare_summaries_reports_percentage_change() -> None:
    before = {"hitAtK": 0.5, "latencyP95": 0.0}
    after = {"hitAtK": 0.75, "latencyP95": 100.0}

    rows = {row["metric"]: row for row in compare_summaries(before, after)}

    assert rows["hitAtK"]["changePct"] == pytest.approx(50.0)
    assert rows["latencyP95"]["changePct"] is None
    assert percent_change(0.0, 0.0) == 0.0
