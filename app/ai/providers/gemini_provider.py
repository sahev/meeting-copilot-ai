from __future__ import annotations

import logging
import json
import time

import httpx

from app.ai.providers.base_provider import BaseAiProvider


LOGGER = logging.getLogger(__name__)


class GeminiProvider(BaseAiProvider):
    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, prompt: str, payload: dict) -> str:
        request_body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{prompt}\n\nPayload JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
                                "Return only the requested content. Do not wrap JSON in markdown fences."
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            },
        }
        last_error: Exception | None = None
        url = f"{self._api_url}/models/{self._model}:generateContent"
        params = {"key": self._api_key}

        for attempt in range(1, 4):
            try:
                LOGGER.info("Calling Gemini generateContent provider, attempt %s.", attempt)
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(url, params=params, json=request_body)
                    response.raise_for_status()
                LOGGER.info("Gemini provider returned HTTP %s.", response.status_code)
                return _extract_gemini_text(response)
            except Exception as exc:
                last_error = exc
                LOGGER.exception("Gemini provider request failed on attempt %s.", attempt)
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        assert last_error is not None
        raise RuntimeError(f"Gemini provider failed after retries: {last_error}") from last_error


def _extract_gemini_text(response: httpx.Response) -> str:
    data = response.json()
    candidates = data.get("candidates")
    if not candidates:
        raise RuntimeError("Gemini response did not contain candidates.")

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_parts = [part.get("text", "") for part in parts if isinstance(part.get("text"), str)]
    text = "\n".join(part for part in text_parts if part.strip()).strip()
    if not text:
        raise RuntimeError("Gemini response did not contain text parts.")
    return text
