from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _project_root() -> Path:
    """Repo root locally, /app inside the container (no .git / .env.example)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env.example").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def _env_files(env: str | None = None) -> tuple[str, ...]:
    """Base .env first, then the environment specific file (last one wins)."""
    root = _project_root()
    files = [str(root / ".env"), str(Path.cwd() / ".env")]
    if env:
        files.extend([str(root / f".env.{env}"), str(Path.cwd() / f".env.{env}")])
    return tuple(files)


class Settings(BaseSettings):
    """Single source of truth for configuration.

    Structural problems fail fast at startup. Missing LLM credentials do not
    crash the process: health reports the LLM as not configured and chat will
    answer with a typed 503 once that module is implemented.
    """

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment: .env + .env.{ENV} are loaded, process env has priority.
    env: str = "local"
    app_name: str = "Croupier RAG API"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False
    api_prefix: str = ""
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4200"]
    )

    # Storage
    data_dir: Path = Path("./data")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    crop_margin_pt: float = Field(default=12.0, ge=0.0, le=200.0)
    crop_dpi: int = Field(default=150, ge=72, le=600)
    image_min_size_pt: float = Field(default=50.0, ge=0.0, le=2000.0)
    image_dpi: int = Field(default=150, ge=72, le=600)

    # Infrastructure
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "manual_chunks"
    job_state_prefix: str = "croupier:job:"
    job_events_prefix: str = "croupier:job-events:"
    job_state_ttl_seconds: int = Field(default=86_400, ge=60)

    # LLM: LLM_PROVIDER decides the adapter (gemini | ollama | openai | deepseek).
    llm_provider: Literal["gemini", "ollama", "openai", "deepseek"] = "gemini"
    llm_model: str = "gemini-flash-latest"
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_thinking_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"

    # Embeddings: fastembed (local), ollama or gemini.
    embedding_provider: Literal["fastembed", "ollama", "gemini"] = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    embedding_dim: int = Field(default=768, ge=1)
    sparse_embedding_model: str = "Qdrant/bm25"
    sparse_embedding_language: str = "spanish"

    # Chunking / retrieval
    chunk_max_tokens: int = Field(default=450, ge=50, le=4000)
    chunk_overlap_tokens: int = Field(default=60, ge=0, le=1000)
    embed_batch_size: int = Field(default=32, ge=1, le=512)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    retrieval_prefetch_limit: int = Field(default=30, ge=1, le=500)
    retrieval_min_score: float = Field(default=0.30, ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, ge=1, le=1000)

    # Selection / context packing (dynamic mode)
    selection_mode: Literal["static", "dynamic"] = "static"
    context_format: Literal["compact", "verbose"] = "verbose"
    candidate_pool: int = Field(default=20, ge=1, le=100)
    min_k: int = Field(default=3, ge=1, le=50)
    max_k: int = Field(default=6, ge=1, le=50)
    rel_ratio: float = Field(default=0.55, ge=0.0, le=1.0)
    gap_ratio: float = Field(default=0.35, ge=0.0, le=1.0)
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    mmr_duplicate_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    context_token_budget: int = Field(default=1800, ge=100, le=100_000)
    token_estimate_factor: float = Field(default=1.32, ge=1.0, le=3.0)
    gate_safety_margin: float = Field(default=0.05, ge=0.0, le=0.5)

    # Resilience (seconds unless stated otherwise)
    llm_timeout_s: float = Field(default=60.0, gt=0)
    embedding_timeout_s: float = Field(default=90.0, gt=0)
    vector_store_timeout_s: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=0, le=10)
    http_retry_base_s: float = Field(default=0.4, gt=0)
    http_retry_max_s: float = Field(default=8.0, gt=0)
    breaker_failure_threshold: int = Field(default=5, ge=1)
    breaker_recovery_s: float = Field(default=30.0, gt=0)

    # Chat / conversations
    chat_history_turns: int = Field(default=6, ge=1, le=50)
    conversation_prefix: str = "croupier:conversation:"
    conversation_ttl_seconds: int = Field(default=86_400, ge=60)

    # Jobs / SSE
    sse_heartbeat_s: float = Field(default=15.0, gt=0)
    ingestion_max_retries: int = Field(default=3, ge=0, le=10)
    ingestion_retry_base_s: float = Field(default=2.0, gt=0)
    ingestion_retry_max_s: float = Field(default=60.0, gt=0)
    ingestion_soft_time_limit_s: int = Field(default=1800, ge=30)
    ingestion_time_limit_s: int = Field(default=1860, ge=30)

    @field_validator("env")
    @classmethod
    def _validate_env_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", normalized):
            raise ValueError("ENV must match [a-z][a-z0-9_-]*")
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed: Any = json.loads(raw)
            return parsed
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @field_validator("api_prefix")
    @classmethod
    def _normalize_api_prefix(cls, value: str) -> str:
        prefix = "/" + value.strip().strip("/")
        return "" if prefix == "/" else prefix

    @field_validator(
        "gemini_api_key",
        "openai_api_key",
        "deepseek_api_key",
        "qdrant_api_key",
        mode="before",
    )
    @classmethod
    def _empty_secret_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "llm_model",
        "embedding_model",
        "sparse_embedding_model",
        "sparse_embedding_language",
        "ollama_base_url",
        "deepseek_base_url",
        "qdrant_url",
        "redis_url",
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("redis_url")
    @classmethod
    def _redis_scheme(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL must start with redis://, rediss:// or unix://")
        return value

    @field_validator("qdrant_url", "ollama_base_url", "deepseek_base_url")
    @classmethod
    def _http_scheme(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL")
        return value

    @model_validator(mode="after")
    def _validate_consistency(self) -> Settings:
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be lower than CHUNK_MAX_TOKENS")
        if self.http_retry_max_s < self.http_retry_base_s:
            raise ValueError("HTTP_RETRY_MAX_S must be >= HTTP_RETRY_BASE_S")
        if self.retrieval_prefetch_limit < self.retrieval_top_k:
            raise ValueError("RETRIEVAL_PREFETCH_LIMIT must be >= RETRIEVAL_TOP_K")
        if self.candidate_pool < self.retrieval_top_k:
            raise ValueError("CANDIDATE_POOL must be >= RETRIEVAL_TOP_K")
        if self.candidate_pool < self.max_k:
            raise ValueError("CANDIDATE_POOL must be >= MAX_K")
        if self.max_k < self.min_k:
            raise ValueError("MAX_K must be >= MIN_K")
        if self.ingestion_retry_max_s < self.ingestion_retry_base_s:
            raise ValueError("INGESTION_RETRY_MAX_S must be >= INGESTION_RETRY_BASE_S")
        if self.ingestion_time_limit_s <= self.ingestion_soft_time_limit_s:
            raise ValueError(
                "INGESTION_TIME_LIMIT_S must be > INGESTION_SOFT_TIME_LIMIT_S"
            )
        return self

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "ollama":
            return True
        if self.llm_provider == "openai":
            return bool(
                self.openai_api_key and self.openai_api_key.get_secret_value().strip()
            )
        if self.llm_provider == "deepseek":
            return bool(
                self.deepseek_api_key
                and self.deepseek_api_key.get_secret_value().strip()
            )
        return bool(
            self.gemini_api_key and self.gemini_api_key.get_secret_value().strip()
        )

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base = Settings(_env_file=_env_files())
    root = _project_root()
    has_specific_file = (root / f".env.{base.env}").exists() or (
        Path.cwd() / f".env.{base.env}"
    ).exists()
    if not has_specific_file:
        return base
    return Settings(_env_file=_env_files(base.env))
