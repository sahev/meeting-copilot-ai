from __future__ import annotations

from app.ai.providers.openai_compatible_provider import OpenAiCompatibleProvider


class GroqProvider(OpenAiCompatibleProvider):
    def __init__(self, api_url: str, api_key: str, model: str) -> None:
        super().__init__(
            api_url=api_url,
            api_key=api_key,
            model=model,
            provider_name="Groq",
        )
