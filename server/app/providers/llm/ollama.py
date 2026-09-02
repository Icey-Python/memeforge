"""Ollama LLM connector (local models).

Talks to a local Ollama daemon via its native /api/chat endpoint:
https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
from typing import Optional

import httpx

from app.core import settings
from app.providers.llm.base import BaseLLMProvider, GeneratedScript


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

    async def generate_script(
        self, topic: str, tone: str = "reddit-commenter", max_lines: int = 8
    ) -> GeneratedScript:
        if not self.is_configured():
            raise RuntimeError("Ollama provider has no base URL configured")

        prompt = (
            f'Write a {tone} vertical video script about "{topic}". '
            "Respond ONLY with JSON: "
            f'{{"title": "<r/gaming style title>", "lines": ["...", ...]}} with '
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
            title=str(parsed.get("title", f"r/gaming on {topic}")),
            lines=lines[:max_lines],
        )
