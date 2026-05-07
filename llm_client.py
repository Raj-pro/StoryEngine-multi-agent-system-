from __future__ import annotations
import json
import logging
import os
import re
from typing import Any

import ollama
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from model output that may have surrounding prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Find the outermost {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No valid JSON found in model output:\n{text[:300]}")


class LLMClient:
    """
    Thin wrapper around the Ollama Python SDK.
    Two modes:
      - complete()      → prose text (high temperature, no JSON constraint)
      - complete_json() → structured dict (low temperature, JSON mode, retried)
    """

    def __init__(self):
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "mistral")
        self._client = ollama.Client(host=host)
        logger.debug(f"LLMClient: model={self.model} host={host}")

    def _chat(self, messages: list[dict], json_mode: bool, temperature: float, num_ctx: int) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "options": ollama.Options(temperature=temperature, num_ctx=num_ctx),
        }
        if json_mode:
            kwargs["format"] = "json"
        response = self._client.chat(**kwargs)
        # Handle both dict and object response shapes across ollama SDK versions
        if hasattr(response, "message"):
            return response.message.content
        return response["message"]["content"]

    def complete(
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.75,
        num_ctx: int = 4096,
    ) -> str:
        """Prose generation — returns raw text."""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        return self._chat(msgs, json_mode=False, temperature=temperature, num_ctx=num_ctx)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    def complete_json(
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.1,
        num_ctx: int = 4096,
    ) -> dict:
        """Structured generation — returns a parsed dict. Retried up to 3×."""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        raw = self._chat(msgs, json_mode=True, temperature=temperature, num_ctx=num_ctx)
        return _extract_json(raw)
