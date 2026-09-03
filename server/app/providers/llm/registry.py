"""LLM provider registry.

Resolves a provider name (+ optional per-request overrides coming from the
frontend model connector node) to a concrete connector instance.
"""

from typing import Dict, Optional, Type
from urllib.parse import urlparse

from fastapi import HTTPException

from app.core import settings
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.openai_compatible import OpenAICompatibleProvider

_REGISTRY: Dict[str, Type[BaseLLMProvider]] = {
    "openai": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
    "mock": MockLLMProvider,
}

# Named OpenAI-compatible gateways: when a request points base_url at one
# of these hosts but supplies no api_key, the matching env key below is
# used instead of the generic OPENAI_API_KEY.
_GATEWAY_KEYS = {
    "openrouter.ai": "OPENROUTER_API_KEY",
    "groq.com": "GROQ_API_KEY",
    "anthropic.com": "ANTHROPIC_API_KEY",
}


def _gateway_default_key(base_url: Optional[str]) -> Optional[str]:
    """Server-side env key matching a gateway base_url, if configured."""
    if not base_url:
        return None
    host = (urlparse(base_url).hostname or "").lower()
    for marker, attr in _GATEWAY_KEYS.items():
        if marker in host:
            return getattr(settings, attr, "") or None
    return None


def get_llm_provider(
    name: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMProvider:
    """Build a provider instance; raises 400 for unknown providers.

    Credential priority: request `api_key` (client key vault / inline
    input) → gateway-matching env key (OPENROUTER/GROQ/ANTHROPIC) → the
    provider's own .env default (OPENAI_API_KEY).
    """
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
    resolved_key = api_key or _gateway_default_key(base_url)
    return provider_cls(model=model, base_url=base_url, api_key=resolved_key)


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
