from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.ai.providers.base_provider import BaseAiProvider


LOGGER = logging.getLogger(__name__)


class StackSpotProvider(BaseAiProvider):
    def __init__(
        self,
        auth_url: str,
        client_id: str,
        client_secret: str,
        agent_url: str,
        agent_id: str,
        use_conversation: bool = False,
        streaming: bool = False,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._agent_url = agent_url.rstrip("/")
        self._agent_id = agent_id
        self._use_conversation = use_conversation
        self._streaming = streaming
        self._timeout_seconds = timeout_seconds
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._conversation_id: str | None = None
        self._total_consumed_tokens = 0

    @property
    def total_consumed_tokens(self) -> int:
        return self._total_consumed_tokens

    def generate(self, prompt: str, payload: dict) -> str:
        request_body = self._build_chat_request(prompt, payload)
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                token = self._get_access_token()
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                LOGGER.info("Calling StackSpot Agent API, attempt %s.", attempt)
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(self._chat_url, headers=headers, json=request_body)
                    if response.status_code == 401 and attempt == 1:
                        self._clear_access_token()
                        continue
                    response.raise_for_status()
                LOGGER.info("StackSpot Agent API returned HTTP %s.", response.status_code)
                return self._extract_text_response(response)
            except Exception as exc:
                last_error = exc
                LOGGER.exception("StackSpot Agent API request failed on attempt %s.", attempt)
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        assert last_error is not None
        raise RuntimeError(f"StackSpot Agent API failed after retries: {last_error}") from last_error

    @property
    def _chat_url(self) -> str:
        return f"{self._agent_url}/v1/agent/{self._agent_id}/chat"

    def _build_chat_request(self, prompt: str, payload: dict) -> dict[str, Any]:
        user_prompt = f"{prompt}\n\nPayload JSON:\n{json.dumps(payload, ensure_ascii=False)}"
        request_body: dict[str, Any] = {
            "streaming": self._streaming,
            "user_prompt": user_prompt,
            "stackspot_knowledge": True,
            "return_ks_in_response": False,
        }
        if self._use_conversation:
            request_body["use_conversation"] = True
            if self._conversation_id:
                request_body["conversation_id"] = self._conversation_id
        return request_body

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at - 30:
            return self._access_token

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self._client_id,
            "grant_type": "client_credentials",
            "client_secret": self._client_secret,
        }
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(self._auth_url, headers=headers, data=data)
            response.raise_for_status()

        token_response = response.json()
        access_token = token_response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("StackSpot auth response did not include access_token.")

        expires_in = token_response.get("expires_in")
        try:
            token_lifetime = float(expires_in)
        except (TypeError, ValueError):
            token_lifetime = 300.0
        self._access_token = access_token
        self._access_token_expires_at = now + token_lifetime
        return access_token

    def _clear_access_token(self) -> None:
        self._access_token = None
        self._access_token_expires_at = 0.0

    def _extract_text_response(self, response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            return response.text

        data: Any = response.json()
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            self._record_token_usage(data)
            conversation_id = data.get("conversation_id")
            if isinstance(conversation_id, str) and conversation_id:
                self._conversation_id = conversation_id
            message = data.get("message")
            if isinstance(message, str):
                return message
            for key in ("output", "content", "text", "answer", "response"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
            return json.dumps(data, ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)

    def _record_token_usage(self, data: dict[str, Any]) -> None:
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            return

        consumed = 0
        for value in tokens.values():
            if isinstance(value, int | float):
                consumed += int(value)
            elif isinstance(value, str):
                try:
                    consumed += int(float(value))
                except ValueError:
                    continue

        self._total_consumed_tokens += consumed
