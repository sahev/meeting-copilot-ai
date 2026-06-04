from __future__ import annotations

from app.ai.providers.http_provider import HttpJsonProvider


class DevinProvider(HttpJsonProvider):
    def __init__(self, api_url: str, api_key: str) -> None:
        super().__init__(api_url=api_url, api_key=api_key, provider_name="Devin")
