from __future__ import annotations

import json
from typing import Any


def parse_json_object(raw_response: str) -> dict[str, Any]:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object.")
    return data
