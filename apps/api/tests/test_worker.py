from __future__ import annotations

import pytest

from app import worker


def test_worker_embedding_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    sentinel = object()

    def fake_build_embedding(_settings: object) -> object:
        calls.append(sentinel)
        return sentinel

    worker._worker_embedding.cache_clear()
    monkeypatch.setattr(worker, "build_embedding", fake_build_embedding)
    try:
        assert worker._worker_embedding() is sentinel
        assert worker._worker_embedding() is sentinel
        assert calls == [sentinel]
    finally:
        worker._worker_embedding.cache_clear()
