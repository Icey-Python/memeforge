"""LLM provider registry.

Resolves a provider name (+ optional per-request overrides coming from the
frontend model connector node) to a concrete connector instance.
"""

from typing import Dict, Optional, Type

from fastapi import HTTPException

from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.openai_compatible import OpenAICompatibleProvider

_REGISTRY: Dict[str, Type[BaseLLMProvider]] = {
    "openai": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
    "mock": MockLLMProvider,
}


def get_llm_provider(
    name: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMProvider:
    """Build a provider instance; raises 400 for unknown providers."""
    provider_cls = _REGISTRY.get(name)
    if provider_cls is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown LLM provider '{name}'. "
                f"Available: {', '.join(sorted(_REGISTRY))}"
            ),
        )
    if name == "ollama":
        return provider_cls(model=model, base_url=base_url)
    return provider_cls(model=model, base_url=base_url, api_key=api_key)


def list_llm_providers() -> list[dict]:
    """Catalog endpoint payload: which connectors exist and are usable."""
    from app.core import settings

    instances = {
        "openai": OpenAICompatibleProvider(),
        "ollama": OllamaProvider(),
        "mock": MockLLMProvider(),
    }
    return [
        {
            "id": pid,
            "label": {
                "openai": "OpenAI-compatible (cloud or local)",
                "ollama": "Ollama (local models)",
                "mock": "Mock (offline, no model)",
            }[pid],
            "default_model": (
                settings.OPENAI_MODEL if pid == "openai"
                else settings.OLLAMA_MODEL if pid == "ollama"
                else "memeforge-stub"
            ),
            "configured": inst.is_configured(),
        }
        for pid, inst in instances.items()
    ]
