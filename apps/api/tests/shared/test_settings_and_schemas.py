from __future__ import annotations

from pathlib import Path

import pytest

import app.config.settings as settings_module
from app.config.settings import Settings
from app.shared.schemas import CamelModel, to_camel


class SampleSchema(CamelModel):
    request_id: str
    section_path: list[str]


def test_to_camel_handles_snake_case() -> None:
    assert to_camel("request_id") == "requestId"
    assert to_camel("section_path") == "sectionPath"
    assert to_camel("status") == "status"
    assert to_camel("dense_rank") == "denseRank"


def test_camel_model_serializes_with_aliases() -> None:
    schema = SampleSchema(request_id="abc", section_path=["A", "B"])

    assert schema.model_dump(by_alias=True) == {
        "requestId": "abc",
        "sectionPath": ["A", "B"],
    }
    assert schema.model_dump() == {
        "request_id": "abc",
        "section_path": ["A", "B"],
    }


def test_camel_model_accepts_both_names() -> None:
    snake = SampleSchema(request_id="abc", section_path=[])
    camel = SampleSchema(requestId="abc", sectionPath=[])

    assert snake == camel


def test_settings_defaults_and_derived_flags() -> None:
    settings = Settings(_env_file=None)

    assert settings.env == "local"
    assert settings.llm_provider == "gemini"
    assert settings.llm_configured is False
    assert settings.embedding_provider == "fastembed"
    assert settings.embedding_dim == 768
    assert settings.api_prefix == ""
    assert settings.llm_timeout_s == 60
    assert settings.breaker_failure_threshold == 5
    assert settings.breaker_recovery_s == 30
    assert settings.selection_mode == "static"
    assert settings.context_format == "verbose"
    assert settings.candidate_pool == 20
    assert settings.context_token_budget == 1800
    assert settings.token_estimate_factor == 1.32
    assert settings.resolved_data_dir.is_absolute()


def test_settings_parse_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_settings_parse_json_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test"]')

    assert Settings(_env_file=None).cors_origins == ["http://a.test"]


def test_settings_reject_inconsistent_chunking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "100")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "100")

    with pytest.raises(ValueError, match="CHUNK_OVERLAP_TOKENS"):
        Settings(_env_file=None)


def test_settings_validate_selection_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANDIDATE_POOL", "4")
    monkeypatch.setenv("RETRIEVAL_TOP_K", "8")

    with pytest.raises(ValueError, match="CANDIDATE_POOL"):
        Settings(_env_file=None)


def test_settings_validate_infrastructure_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "http://not-redis")
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(_env_file=None)

    monkeypatch.delenv("REDIS_URL")
    monkeypatch.setenv("QDRANT_URL", "qdrant:6333")
    with pytest.raises(ValueError, match="http"):
        Settings(_env_file=None)


def test_settings_validate_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "Not Valid!")

    with pytest.raises(ValueError, match="ENV"):
        Settings(_env_file=None)


def test_settings_normalize_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PREFIX", "api/v1/")

    assert Settings(_env_file=None).api_prefix == "/api/v1"


def test_empty_gemini_key_means_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")

    settings = Settings(_env_file=None)

    assert settings.gemini_api_key is None
    assert settings.llm_configured is False


def test_ollama_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    assert Settings(_env_file=None).llm_configured is True


def test_openai_provider_uses_its_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert Settings(_env_file=None).llm_configured is False

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert Settings(_env_file=None).llm_configured is True


def test_deepseek_provider_uses_its_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    assert Settings(_env_file=None).llm_configured is False

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    assert Settings(_env_file=None).llm_configured is True


def test_invalid_provider_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    with pytest.raises(ValueError, match="ollama"):
        Settings(_env_file=None)


def test_env_specific_file_overrides_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path
    (root / ".env").write_text("ENV=test\nLLM_MODEL=base-model\n", encoding="utf-8")
    (root / ".env.test").write_text("LLM_MODEL=env-specific-model\n", encoding="utf-8")

    monkeypatch.setattr(settings_module, "_project_root", lambda: root)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.env == "test"
    assert settings.llm_model == "env-specific-model"
