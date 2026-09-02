"""TTS provider registry."""

from typing import Dict, List, Optional, Type

from fastapi import HTTPException

from app.providers.tts.base import BaseTTSProvider, Voice
from app.providers.tts.edge import EdgeTTSProvider
from app.providers.tts.azure import AzureTTSProvider
from app.providers.tts.elevenlabs import ElevenLabsProvider

_REGISTRY: Dict[str, Type[BaseTTSProvider]] = {
    "edge": EdgeTTSProvider,
    "azure": AzureTTSProvider,
    "elevenlabs": ElevenLabsProvider,
}


def get_tts_provider(name: str, voice: Optional[str] = None) -> BaseTTSProvider:
    """Build a TTS provider instance; raises 400 for unknown providers."""
    provider_cls = _REGISTRY.get(name)
    if provider_cls is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown TTS provider '{name}'. "
                f"Available: {', '.join(sorted(_REGISTRY))}"
            ),
        )
    return provider_cls(voice=voice)


async def list_tts_voices(name: str) -> List[Voice]:
    """Voices for the voice picker on the frontend voiceover node."""
    provider = get_tts_provider(name)
    if isinstance(provider, ElevenLabsProvider):
        return await provider.list_remote_voices()
    return provider.list_voices()
