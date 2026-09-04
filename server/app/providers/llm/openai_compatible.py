"""OpenAI-compatible LLM connector.

Works with OpenAI, Ollama's OpenAI-compat endpoint, LM Studio, vLLM,
OpenRouter, and any server that implements `POST /chat/completions`.
Uses httpx directly so no vendor SDK is required.
"""

import json
from typing import List, Optional

import httpx

from app.core import settings
from app.providers.llm.base import (
    BaseLLMProvider,
    DiscoveredModel,
    GeneratedScript,
    word_target,
)


class OpenAICompatibleProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, model: Optional[str] = None,
                 base_url: Optional[str] = None,
                 api_key: Optional[str] = None) -> None:
        super().__init__(
            model=model or settings.OPENAI_MODEL,
            base_url=base_url or settings.OPENAI_BASE_URL,
            api_key=api_key or settings.OPENAI_API_KEY,
        )

    def is_configured(self) -> bool:
        # An explicit api_key can be empty for local OpenAI-compatible
        # servers (LM Studio, vLLM), so only the URL is required.
        return bool(self.base_url)

    async def list_models(self) -> List[DiscoveredModel]:
        """Live model discovery via the OpenAI-compatible GET /models."""
        if not self.is_configured():
            raise RuntimeError("OpenAI-compatible provider has no base URL configured")

        url = f"{self.base_url.rstrip('/')}/models"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # OpenAI-style {"data": [...]}; some servers return a bare list or
        # {"models": [...]} — accept all three shapes.
        items = (
            data if isinstance(data, list) else data.get("data") or data.get("models") or []
        )
        models: List[DiscoveredModel] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("name") or "").strip()
            if not model_id:
                continue
            models.append(
                DiscoveredModel(
                    id=model_id,
                    label=model_id,
                    family=item.get("owned_by"),
                )
            )
        models.sort(key=lambda m: m.id.lower())
        return models

    async def complete_json(self, system: str, user: str) -> dict:
        """Single-shot JSON completion (json_object response format)."""
        return await self._chat_completion_json(system, user, temperature=0.3)

    async def _chat_completion_json(self, system: str, user: str,
                                    temperature: float) -> dict:
        """POST /chat/completions with JSON mode; returns the parsed dict."""
        if not self.is_configured():
            raise RuntimeError("OpenAI-compatible provider has no base URL configured")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def generate_script(
        self, topic: str, tone: str = "casual-commenter", max_lines: int = 8,
        duration_target: int = 60,
    ) -> GeneratedScript:
        if not self.is_configured():
            raise RuntimeError("OpenAI-compatible provider has no base URL configured")

        w_min, w_max = word_target(duration_target)
        system = (
            f"You write {tone} vertical video scripts for "
            "short-form platforms (YouTube Shorts, TikTok, "
            "Reels). Target "
            f"{duration_target} seconds of spoken speech — "
            f"roughly {w_min}-{w_max} words in total. "
            "Also produce 10-14 visual stock-video search phrases "
            "(2-4 words each, concrete subjects/actions a stock site "
            "like Pexels would return vertical b-roll for), ordered by "
            "their appearance in the script. "
            f'Output JSON: {{"title": string, "lines": '
            f"string[{max_lines}], "
            '"keywords": string[10..14]}. '
            "Short spoken lines, 1-12 words each, last line is "
            "a punchline. No markdown."
        )
        parsed = await self._chat_completion_json(
            system, f"Topic: {topic}", temperature=0.9
        )
        lines: List[str] = [str(line).strip() for line in parsed.get("lines", []) if str(line).strip()]
        if not lines:
            raise ValueError("LLM response contained no usable lines")
        keywords = [
            str(k).strip().lower()
            for k in parsed.get("keywords", [])
            if str(k).strip()
        ]
        return GeneratedScript(
            title=str(parsed.get("title") or f"the {topic} take"),
            lines=lines[:max_lines],
            keywords=list(dict.fromkeys(keywords)),
        )
