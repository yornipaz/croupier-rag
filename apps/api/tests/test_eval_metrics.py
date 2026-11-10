from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.metrics import (  # noqa: E402
    aggregate_question_runs,
    compare_summaries,
    evaluate_question,
    median_metrics,
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
    "split": "test",
}

CASE_REFUSAL = {
    "id": "q2",
    "question": "¿Fuera del corpus?",
    "expected_pages": [],
    "needs_figure": False,
    "should_refuse": True,
    "split": "test",
}


def _usage(**overrides: int | str | bool) -> dict[str, int | str | bool]:
    usage: dict[str, int | str | bool] = {
        "chunksRetrieved": 3,
        "chunksSent": 2,
        "systemTokens": 40,
        "historyTokens": 5,
        "contextTokens": 100,
        "questionTokens": 6,
        "promptTemplateTokens": 9,
        "promptEstimatedTokens": 160,
        "promptTokens": 180,
        "promptGapTokens": 20,
        "completionTokens": 20,
        "promptSource": "provider",
        "completionSource": "provider",
        "breakdownSource": "estimated",
        "llmCalls": 1,
        "latencyMs": 500,
        "llmCalled": True,
    }
    usage.update(overrides)
    return usage


def _response(
    *,
    sufficient: bool,
    source_pages: list[int],
    sent_pages: list[int] | None = None,
    retrieved_pages: list[int] | None = None,
    dense_cosines: list[float] | None = None,
    image_count: int = 0,
    usage: dict[str, int | str | bool] | None = None,
) -> dict[str, object]:
    retrieved = retrieved_pages if retrieved_pages is not None else source_pages
    sent = sent_pages if sent_pages is not None else retrieved
    cosines = dense_cosines or [0.9 - index * 0.1 for index in range(len(retrieved))]
    return {
        "sufficient": sufficient,
        "sources": [{"page": page} for page in source_pages],
        "images": [{"url": f"image-{index}"} for index in range(image_count)],
        "usage": usage or _usage(),
        "debug": {
            "retrieved": [
                {
                    "chunkId": f"chunk-{index}",
                    "page": page,
                    "fusedScore": 0.02,
                    "denseCosine": cosines[index],
                    "denseRank": index + 1,
                    "sparseRank": None,
                    "sent": page in sent,
                }
                for index, page in enumerate(retrieved)
            ]
        },
    }


def test_answer_hit_uses_cited_sources() -> None:
    row = evaluate_question(
        CASE_ANSWERABLE,
        _response(sufficient=True, source_pages=[9, 5], image_count=1),
    )

    assert row["answerHit"] is True
    assert row["retrievalHit"] is True
    assert row["figureHit"] is True
    assert row["refusalCorrect"] is True
    assert row["sourcePages"] == [9, 5]

    miss = evaluate_question(
        CASE_ANSWERABLE,
        _response(sufficient=True, source_pages=[9], image_count=1),
    )
    assert miss["answerHit"] is False


def test_retrieval_hit_uses_sent_retrieved_pages_not_citations() -> None:
    row = evaluate_question(
        CASE_ANSWERABLE,
        _response(
            sufficient=True,
            source_pages=[9],
            retrieved_pages=[4, 9],
            sent_pages=[4, 9],
        ),
    )

    assert row["answerHit"] is False
    assert row["retrievalHit"] is True
    assert row["sentPages"] == [4, 9]


def test_retrieval_hit_ignores_candidates_not_sent_to_the_llm() -> None:
    row = evaluate_question(
        CASE_ANSWERABLE,
        _response(
            sufficient=True,
            source_pages=[9],
            retrieved_pages=[4, 9],
            sent_pages=[9],
        ),
    )

    assert row["retrievalHit"] is False


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
    assert correct["answerHit"] is None
    assert correct["retrievalHit"] is None
    assert correct["figureHit"] is None
    assert wrong["refusalCorrect"] is False


def test_summarize_computes_retrieval_tokens_and_dense_separation() -> None:
    rows = [
        evaluate_question(
            CASE_ANSWERABLE,
            _response(
                sufficient=True,
                source_pages=[4],
                sent_pages=[4],
                image_count=1,
                dense_cosines=[0.8],
                usage=_usage(
                    chunksSent=2,
                    contextTokens=10,
                    promptTokens=100,
                    promptEstimatedTokens=80,
                    promptGapTokens=20,
                    latencyMs=100,
                ),
            ),
        ),
        evaluate_question(
            CASE_ANSWERABLE,
            _response(
                sufficient=True,
                source_pages=[9],
                retrieved_pages=[4, 9],
                sent_pages=[4],
                image_count=0,
                dense_cosines=[0.35, 0.35],
                usage=_usage(
                    chunksSent=4,
                    contextTokens=20,
                    promptTokens=200,
                    promptEstimatedTokens=180,
                    promptGapTokens=20,
                    latencyMs=200,
                ),
            ),
        ),
        evaluate_question(
            CASE_REFUSAL,
            _response(
                sufficient=False,
                source_pages=[],
                retrieved_pages=[3],
                sent_pages=[3],
                dense_cosines=[0.25],
                usage=_usage(
                    chunksSent=0,
                    contextTokens=30,
                    promptTokens=0,
                    promptEstimatedTokens=0,
                    promptGapTokens=0,
                    completionTokens=0,
                    latencyMs=300,
                    llmCalled=False,
                ),
            ),
        ),
    ]

    metrics = summarize(rows)

    assert metrics["questions"] == 3
    assert metrics["errors"] == 0
    assert metrics["answerHit"] == pytest.approx(0.5)
    assert metrics["retrievalHit"] == pytest.approx(1.0)
    assert metrics["figureHit"] == pytest.approx(0.5)
    assert metrics["refusalCorrect"] == pytest.approx(1.0)
    assert metrics["llmCallRate"] == pytest.approx(2 / 3)
    assert metrics["contextTokensMean"] == pytest.approx(20.0)
    assert metrics["contextTokensP95"] == pytest.approx(29.0)
    assert metrics["promptTokensMean"] == pytest.approx(100.0)
    assert metrics["promptGapMean"] == pytest.approx(20.0)
    assert metrics["chunksSentMean"] == pytest.approx(2.0)
    assert metrics["chunksSentP95"] == pytest.approx(3.8)
    assert metrics["denseCosineAnswerableP50"] == pytest.approx(0.575)
    assert metrics["denseCosineRefusalP50"] == pytest.approx(0.25)
    assert metrics["denseCosineSeparationP50"] == pytest.approx(0.325)
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


def test_median_metrics_uses_the_median_across_runs() -> None:
    runs = [
        {"answerHit": 0.5, "latencyP50": 100.0},
        {"answerHit": 0.75, "latencyP50": 300.0},
        {"answerHit": 0.6, "latencyP50": 200.0},
    ]

    metrics = median_metrics(runs)

    assert metrics["answerHit"] == pytest.approx(0.6)
    assert metrics["latencyP50"] == pytest.approx(200.0)


def test_aggregate_question_runs_uses_majority_and_medians() -> None:
    first = [
        evaluate_question(CASE_ANSWERABLE, _response(sufficient=True, source_pages=[4])),
        evaluate_question(CASE_REFUSAL, _response(sufficient=False, source_pages=[])),
    ]
    second = [
        evaluate_question(CASE_ANSWERABLE, _response(sufficient=True, source_pages=[9])),
        evaluate_question(CASE_REFUSAL, _response(sufficient=False, source_pages=[])),
    ]
    third = [
        evaluate_question(CASE_ANSWERABLE, _response(sufficient=True, source_pages=[4])),
        evaluate_question(CASE_REFUSAL, _response(sufficient=False, source_pages=[])),
    ]

    rows = aggregate_question_runs([first, second, third])

    assert rows[0]["answerHit"] is True
    assert rows[0]["sourcePages"] == [4, 9]
    assert rows[0]["usage"]["latencyMs"] == 500
    assert rows[1]["refusalCorrect"] is True


def test_compare_summaries_reports_percentage_change() -> None:
    before = {"answerHit": 0.5, "latencyP95": 0.0}
    after = {"answerHit": 0.75, "latencyP95": 100.0}

    rows = {row["metric"]: row for row in compare_summaries(before, after)}

    assert rows["answerHit"]["changePct"] == pytest.approx(50.0)
    assert rows["latencyP95"]["changePct"] is None
    assert percent_change(0.0, 0.0) == 0.0
