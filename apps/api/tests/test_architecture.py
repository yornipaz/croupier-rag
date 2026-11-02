from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest
from fastapi import APIRouter

MODULES = ("documents", "ingestion", "ai", "vector_store", "retrieval", "chat", "health")


@pytest.mark.parametrize("module_name", MODULES)
def test_module_exposes_router_and_factories(module_name: str) -> None:
    module = importlib.import_module(f"app.modules.{module_name}.module")

    assert isinstance(module.router, APIRouter)
    assert callable(getattr(module, f"build_{module_name}_router"))
    assert callable(getattr(module, f"build_{module_name}_module"))


def test_no_cross_module_infrastructure_imports() -> None:
    """Rule 3: modules never import another module's adapters."""
    modules_root = Path(__file__).resolve().parents[1] / "app" / "modules"
    violations: list[str] = []

    for path in modules_root.rglob("*.py"):
        current_module = path.relative_to(modules_root).parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                candidates = [node.module]

            for candidate in candidates:
                parts = candidate.split(".")
                if len(parts) >= 4 and parts[:2] == ["app", "modules"]:
                    target_module = parts[2]
                    if target_module != current_module and "infrastructure" in parts[3:]:
                        violations.append(f"{path.relative_to(modules_root)} -> {candidate}")

    assert not violations, "Cross-module adapter imports:\n" + "\n".join(violations)
