"""Compatibility checks for evaluation result files (stdlib only)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
COMPATIBILITY_FIELDS: tuple[str, ...] = (
    "schemaVersion",
    "datasetHash",
    "split",
    "nQuestions",
)
FIELD_LABELS = {
    "schemaVersion": "schemaVersion",
    "datasetHash": "datasetHash",
    "split": "split",
    "nQuestions": "nQuestions",
}


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    ok: bool
    differences: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    missing: dict[str, list[str]] = field(default_factory=dict)

    def error_message(self) -> str:
        lines = [
            "No se puede comparar: los resultados son incompatibles.",
        ]
        for field_name, (before, after) in self.differences.items():
            lines.append(
                f"- {FIELD_LABELS[field_name]}: {format_meta(before)} vs {format_meta(after)}"
            )
        lines.append("No se imprime la tabla de comparación.")
        return "\n".join(lines)


def format_meta(value: Any) -> str:
    """Render a metadata value without inventing a numeric fallback."""
    if value is None:
        return "n/d"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return text if text else "n/d"


def check_compatibility(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> CompatibilityReport:
    differences: dict[str, tuple[Any, Any]] = {}
    missing: dict[str, list[str]] = {"before": [], "after": []}
    for field_name in COMPATIBILITY_FIELDS:
        before_value = before.get(field_name)
        after_value = after.get(field_name)
        if before_value is None:
            missing["before"].append(field_name)
        if after_value is None:
            missing["after"].append(field_name)
        if before_value is not None and after_value is not None and before_value != after_value:
            differences[field_name] = (before_value, after_value)
    return CompatibilityReport(
        ok=not differences,
        differences=differences,
        missing=missing,
    )
