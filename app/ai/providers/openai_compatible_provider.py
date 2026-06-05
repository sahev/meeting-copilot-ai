from __future__ import annotations

import logging
import json
import time

import httpx

from app.ai.providers.base_provider import BaseAiProvider


LOGGER = logging.getLogger(__name__)


class OpenAiCompatibleProvider(BaseAiProvider):
    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        provider_name: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._provider_name = provider_name
        self._timeout_seconds = timeout_seconds
        self._total_consumed_tokens = 0

    @property
    def total_consumed_tokens(self) -> int:
        return self._total_consumed_tokens

    def generate(self, prompt: str, payload: dict) -> str:
        request_body = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return exactly what the user prompt requests. Do not wrap JSON in markdown fences.",
                },
                {
                    "role": "user",
                    "content": f"{prompt}\n\nPayload JSON:\n{json.dumps(payload, ensure_ascii=False)}",
                },
            ],
            "temperature": 0.2,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                LOGGER.info("Calling %s chat completions provider, attempt %s.", self._provider_name, attempt)
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(self._api_url, headers=headers, json=request_body)
                    response.raise_for_status()
                LOGGER.info("%s provider returned HTTP %s.", self._provider_name, response.status_code)
                data = response.json()
                self._record_token_usage(data)
                return _extract_chat_completion_text(data)
            except Exception as exc:
                last_error = exc
                LOGGER.exception("%s provider request failed on attempt %s.", self._provider_name, attempt)
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        assert last_error is not None
        raise RuntimeError(f"{self._provider_name} provider failed after retries: {last_error}") from last_error

    def _record_token_usage(self, data: dict) -> None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return
        total_tokens = usage.get("total_tokens")
        if isinstance(total_tokens, int | float):
            self._total_consumed_tokens += int(total_tokens)


def _extract_chat_completion_text(data: dict) -> str:
    choices = data.get("choices")
    if not choices:
        raise RuntimeError("Chat completion response did not contain choices.")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Chat completion response did not contain message content.")
    return content.strip()
