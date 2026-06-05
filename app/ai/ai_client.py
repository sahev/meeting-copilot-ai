from __future__ import annotations

from app.ai.providers.base_provider import BaseAiProvider
from app.ai.providers.devin_provider import DevinProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.groq_provider import GroqProvider
from app.ai.providers.stackspot_provider import StackSpotProvider
from app.config import Settings


def build_ai_provider(settings: Settings) -> BaseAiProvider:
    provider = (settings.ai_provider or "").casefold()
    if (
        provider == "stackspot"
        and settings.stackspot_auth_url
        and settings.stackspot_client_id
        and settings.stackspot_client_secret
        and settings.stackspot_agent_id
    ):
        return StackSpotProvider(
            auth_url=settings.stackspot_auth_url,
            client_id=settings.stackspot_client_id,
            client_secret=settings.stackspot_client_secret,
            agent_url=settings.stackspot_agent_url,
            agent_id=settings.stackspot_agent_id,
            use_conversation=settings.stackspot_use_conversation,
            streaming=settings.stackspot_streaming,
        )
    if provider == "devin" and settings.devin_api_url and settings.devin_api_key:
        return DevinProvider(settings.devin_api_url, settings.devin_api_key)
    if provider == "gemini" and settings.gemini_api_key:
        return GeminiProvider(settings.gemini_api_url, settings.gemini_api_key, settings.gemini_model)
    if provider == "groq" and settings.groq_api_key:
        return GroqProvider(settings.groq_api_url, settings.groq_api_key, settings.groq_model)

    raise RuntimeError(
        "No AI provider is configured. Set AI_PROVIDER plus the matching credentials and model in .env."
    )
