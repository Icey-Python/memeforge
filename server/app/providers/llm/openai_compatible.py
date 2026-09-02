"""OpenAI-compatible LLM connector.

Works with OpenAI, Ollama's OpenAI-compat endpoint, LM Studio, vLLM,
OpenRouter, and any server that implements `POST /chat/completions`.
Uses httpx directly so no vendor SDK is required.
"""

import json
from typing import List, Optional

import httpx

from app.core import settings
from app.providers.llm.base import BaseLLMProvider, GeneratedScript


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

    async def generate_script(
        self, topic: str, tone: str = "reddit-commenter", max_lines: int = 8
    ) -> GeneratedScript:
        if not self.is_configured():
            raise RuntimeError("OpenAI-compatible provider has no base URL configured")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You write {tone} vertical video scripts. Output JSON: "
                        f'{{"title": string, "lines": string[{max_lines}]}}. '
                        "Short spoken lines, 1-12 words each, last line is a punchline. "
                        "No markdown."
                    ),
                },
                {"role": "user", "content": f"Topic: {topic}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.9,
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
        parsed = json.loads(content)
        lines: List[str] = [str(line).strip() for line in parsed.get("lines", []) if str(line).strip()]
        if not lines:
            raise ValueError("LLM response contained no usable lines")
        return GeneratedScript(
            title=str(parsed.get("title", f"r/gaming on {topic}")),
            lines=lines[:max_lines],
        )
