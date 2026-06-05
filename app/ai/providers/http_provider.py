from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.ai.providers.base_provider import BaseAiProvider


LOGGER = logging.getLogger(__name__)


class HttpJsonProvider(BaseAiProvider):
    def __init__(self, api_url: str, api_key: str, provider_name: str, timeout_seconds: float = 60.0) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._provider_name = provider_name
        self._timeout_seconds = timeout_seconds
        self._total_consumed_tokens = 0

    @property
    def total_consumed_tokens(self) -> int:
        return self._total_consumed_tokens

    def generate(self, prompt: str, payload: dict) -> str:
        request_body = {"prompt": prompt, "payload": payload}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                LOGGER.info("Calling %s AI provider, attempt %s.", self._provider_name, attempt)
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(self._api_url, headers=headers, json=request_body)
                    response.raise_for_status()
                LOGGER.info("%s AI provider returned HTTP %s.", self._provider_name, response.status_code)
                text, consumed_tokens = _extract_text_response(response)
                self._total_consumed_tokens += consumed_tokens
                return text
            except Exception as exc:
                last_error = exc
                LOGGER.exception("%s AI provider request failed on attempt %s.", self._provider_name, attempt)
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        assert last_error is not None
        raise RuntimeError(f"{self._provider_name} AI provider failed after retries: {last_error}") from last_error


def _extract_text_response(response: httpx.Response) -> tuple[str, int]:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return response.text, 0

    data: Any = response.json()
    if isinstance(data, str):
        return data, 0
    if isinstance(data, dict):
        consumed_tokens = _extract_consumed_tokens(data)
        for key in ("output", "content", "text", "message", "answer", "response"):
            value = data.get(key)
            if isinstance(value, str):
                return value, consumed_tokens
        return json.dumps(data, ensure_ascii=False), consumed_tokens
    return json.dumps(data, ensure_ascii=False), 0


def _extract_consumed_tokens(data: dict[str, Any]) -> int:
    usage = data.get("usage")
    if isinstance(usage, dict):
        total_tokens = usage.get("total_tokens") or usage.get("totalTokenCount")
        if isinstance(total_tokens, int | float):
            return int(total_tokens)

    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return 0

    consumed = 0
    for value in tokens.values():
        if isinstance(value, int | float):
            consumed += int(value)
        elif isinstance(value, str):
            try:
                consumed += int(float(value))
            except ValueError:
                continue
    return consumed
