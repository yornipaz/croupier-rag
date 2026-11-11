from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.compatibility import (  # noqa: E402
    SCHEMA_VERSION,
    check_compatibility,
    format_meta,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "datasetHash": "abc123",
        "split": "test",
        "nQuestions": 12,
    }
    payload.update(overrides)
    return payload


def test_compatible_payloads_pass() -> None:
    report = check_compatibility(_payload(), _payload())

    assert report.ok is True
    assert report.differences == {}
    assert report.missing == {"before": [], "after": []}


def test_schema_version_mismatch_fails() -> None:
    report = check_compatibility(_payload(), _payload(schemaVersion=SCHEMA_VERSION + 1))

    assert report.ok is False
    assert "schemaVersion" in report.differences
    assert "No se imprime la tabla" in report.error_message()


def test_dataset_hash_mismatch_fails() -> None:
    report = check_compatibility(_payload(), _payload(datasetHash="different"))

    assert report.ok is False
    assert report.differences["datasetHash"] == ("abc123", "different")


def test_split_or_question_count_mismatch_fails() -> None:
    split_report = check_compatibility(_payload(), _payload(split="all"))
    count_report = check_compatibility(_payload(), _payload(nQuestions=11))

    assert split_report.ok is False
    assert count_report.ok is False


def test_missing_fields_are_warnings_and_render_as_nd() -> None:
    old_payload = {"datasetHash": "abc123"}

    report = check_compatibility(old_payload, _payload())

    assert report.ok is True
    assert "schemaVersion" in report.missing["before"]
    assert "nQuestions" in report.missing["before"]
    assert format_meta(old_payload.get("schemaVersion")) == "n/d"
    assert format_meta(0) == "0"
