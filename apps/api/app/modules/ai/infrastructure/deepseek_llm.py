from __future__ import annotations

from app.modules.ai.infrastructure.openai_llm import OpenAILLM


class DeepSeekLLM(OpenAILLM):
    """DeepSeek Chat Completions adapter (OpenAI-compatible API)."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout_s: float = 60.0,
        thinking_enabled: bool = False,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_s=timeout_s,
            provider="deepseek",
            json_schema_supported=False,
            thinking_enabled=thinking_enabled,
        )
