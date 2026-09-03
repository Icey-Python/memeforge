"""Ollama LLM connector (local models).

Talks to a local Ollama daemon via its native /api/chat endpoint:
https://github.com/ollama/ollama/blob/main/docs/api.md
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


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, model: Optional[str] = None,
                 base_url: Optional[str] = None) -> None:
        super().__init__(
            model=model or settings.OLLAMA_MODEL,
            base_url=base_url or settings.OLLAMA_BASE_URL,
        )

    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def list_models(self) -> List[DiscoveredModel]:
        """Live model discovery via Ollama's native /api/tags endpoint."""
        if not self.is_configured():
            raise RuntimeError("Ollama provider has no base URL configured")

        url = f"{self.base_url.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        models: List[DiscoveredModel] = []
        for item in data.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            details = item.get("details") or {}
            models.append(
                DiscoveredModel(
                    id=name,
                    label=name,
                    size_bytes=item.get("size"),
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                    modified_at=item.get("modified_at"),
                )
            )
        return models

    async def generate_script(
        self, topic: str, tone: str = "casual-commenter", max_lines: int = 8,
        duration_target: int = 60,
    ) -> GeneratedScript:
        if not self.is_configured():
            raise RuntimeError("Ollama provider has no base URL configured")

        w_min, w_max = word_target(duration_target)
        prompt = (
            f'Write a {tone} vertical video script about "{topic}" for '
            "short-form platforms (YouTube Shorts, TikTok, Reels). Target "
            f"{duration_target} seconds of spoken speech — roughly "
            f"{w_min}-{w_max} words in total. "
            "Respond ONLY with JSON: "
            f'{{"title": "<short punchy title>", "lines": ["...", ...]}} with '
            f"exactly {max_lines} short spoken lines (1-12 words each). "
            "The last line must be a punchline."
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        }
        url = f"{self.base_url.rstrip('/')}/api/chat"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ollama returned non-JSON script: {content[:200]}") from exc

        lines = [str(l).strip() for l in parsed.get("lines", []) if str(l).strip()]
        if not lines:
            raise ValueError("Ollama response contained no usable lines")
        return GeneratedScript(
            title=str(parsed.get("title") or f"the {topic} take"),
            lines=lines[:max_lines],
        )
