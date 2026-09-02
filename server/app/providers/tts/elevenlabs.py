"""ElevenLabs TTS provider (optional premium tier).

Requires ELEVENLABS_API_KEY. Uses the classic TTS endpoint
(https://api.elevenlabs.io/docs) — swap to the newer `v1/text-to-speech`
flow if you need streaming/low latency.
"""

from typing import List, Optional

import httpx

from app.core import settings
from app.providers.tts.base import BaseTTSProvider, SynthesizedAudio, Voice


class ElevenLabsProvider(BaseTTSProvider):
    name = "elevenlabs"
    API_BASE = "https://api.elevenlabs.io/v1"

    def __init__(self, voice: Optional[str] = None) -> None:
        super().__init__(voice or settings.ELEVENLABS_DEFAULT_VOICE)

    def is_configured(self) -> bool:
        return bool(settings.ELEVENLABS_API_KEY)

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        if not self.is_configured():
            raise RuntimeError("ElevenLabs TTS requires ELEVENLABS_API_KEY")
        url = f"{self.API_BASE}/text-to-speech/{self.voice}"
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        return SynthesizedAudio(
            audio_bytes=resp.content,
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    async def list_remote_voices(self) -> List[Voice]:
        """Fetch the account's voice library (used by the voice picker)."""
        if not self.is_configured():
            return []
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.API_BASE}/voices",
                headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            Voice(
                id=v["voice_id"],
                label=v.get("name", v["voice_id"]),
                language=v.get("labels", {}).get("language", "en"),
                gender=v.get("labels", {}).get("gender", "unknown"),
                tags=list(v.get("labels", {}).get("tags", []) or []),
            )
            for v in data.get("voices", [])
        ]

    def list_voices(self) -> List[Voice]:
        return []
