"""TTS provider registry."""

from typing import Dict, List, Optional, Type

from fastapi import HTTPException

from app.providers.tts.base import BaseTTSProvider, Voice
from app.providers.tts.edge import EdgeTTSProvider
from app.providers.tts.google import GoogleTTSProvider
from app.providers.tts.meme_classic import MemeClassicTTSProvider
from app.providers.tts.tiktok import TikTokTTSProvider
from app.providers.tts.azure import AzureTTSProvider
from app.providers.tts.elevenlabs import ElevenLabsProvider

_REGISTRY: Dict[str, Type[BaseTTSProvider]] = {
    # Free engines first; meme_classic (Brian & the classic cast) is the
    # flagship free meme-voice engine, tiktok is legacy/best-effort.
    "edge": EdgeTTSProvider,
    "meme_classic": MemeClassicTTSProvider,
    "tiktok": TikTokTTSProvider,
    "google": GoogleTTSProvider,
    "azure": AzureTTSProvider,
    "elevenlabs": ElevenLabsProvider,
}


def get_tts_provider(
    name: str,
    voice: Optional[str] = None,
    elevenlabs_api_key: Optional[str] = None,
    azure_speech_key: Optional[str] = None,
    azure_speech_region: Optional[str] = None,
) -> BaseTTSProvider:
    """Build a TTS provider instance; raises 400 for unknown providers.

    Client-supplied credentials (studio key vault) take priority over the
    server .env defaults for the keyed providers (ElevenLabs, Azure).
    """
    provider_cls = _REGISTRY.get(name)
    if provider_cls is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown TTS provider '{name}'. "
                f"Available: {', '.join(sorted(_REGISTRY))}"
            ),
        )
    if provider_cls is ElevenLabsProvider:
        return provider_cls(voice=voice, api_key=elevenlabs_api_key)
    if provider_cls is AzureTTSProvider:
        return provider_cls(
            voice=voice, speech_key=azure_speech_key, region=azure_speech_region
        )
    return provider_cls(voice=voice)


async def list_tts_voices(
    name: str,
    elevenlabs_api_key: Optional[str] = None,
    azure_speech_key: Optional[str] = None,
    azure_speech_region: Optional[str] = None,
) -> List[Voice]:
    """Voices for the voice picker on the frontend voiceover node."""
    provider = get_tts_provider(
        name,
        elevenlabs_api_key=elevenlabs_api_key,
        azure_speech_key=azure_speech_key,
        azure_speech_region=azure_speech_region,
    )
    if isinstance(provider, ElevenLabsProvider):
        return await provider.list_remote_voices()
    return provider.list_voices()
