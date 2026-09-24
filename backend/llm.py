"""Tiny OpenAI JSON client. Policy and numbers stay in Python."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from backend.config import settings


def complete(system: str, user: str) -> tuple[dict[str, Any], int]:
    payload = _post(system, user)
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage") or {}
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM did not return a JSON object")
    return parsed, int(usage.get("total_tokens") or 0)


def _post(system: str, user: str) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": settings.llm_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))
