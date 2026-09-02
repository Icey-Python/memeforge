"""TTS connector base class and shared voice catalog."""

from typing import List, Optional

from pydantic import BaseModel


class SynthesizedAudio(BaseModel):
    """Result of a TTS synthesis call."""

    audio_bytes: bytes
    format: str = "mp3"  # container/extension of audio_bytes
    voice: str
    provider: str


class Voice(BaseModel):
    id: str
    label: str
    language: str
    gender: str
    tags: List[str] = []


class BaseTTSProvider:
    """Contract for voiceover connectors (edge-tts, Azure, ElevenLabs...)."""

    name: str = "base"

    def __init__(self, voice: Optional[str] = None) -> None:
        self.voice = voice

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        raise NotImplementedError

    def list_voices(self) -> List[Voice]:
        return []

    def is_configured(self) -> bool:
        return True
