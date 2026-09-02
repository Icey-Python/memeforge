"""TTS connector base class and shared voice catalog."""

from typing import List, Optional

from pydantic import BaseModel


def chunk_text(text: str, limit: int = 280) -> List[str]:
    """Split text into endpoint-sized chunks (on word boundaries).

    Shared by every provider whose HTTP endpoint hard-caps request text
    length (TikTok WXA ~280 chars, Google translate_tts ~200 chars...).
    Lossless: `" ".join(chunk_text(t)) == " ".join(t.split())`.
    """
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: List[str] = []
    cur = ""
    for word in text.split():
        candidate = f"{cur} {word}".strip()
        if len(candidate) > limit and cur:
            chunks.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


class WordTiming(BaseModel):
    """Exact interval of one spoken word, from a TTS engine that emits
    word-boundary metadata (e.g. Edge-TTS `WordBoundary` events).

    `start`/`end` are seconds relative to the start of the synthesized
    audio stream for that call, so they can be offset by the caller to
    place the word on the final voiceover timeline.
    """

    text: str
    start: float  # seconds
    end: float  # seconds


class SynthesizedAudio(BaseModel):
    """Result of a TTS synthesis call."""

    audio_bytes: bytes
    format: str = "mp3"  # container/extension of audio_bytes
    voice: str
    provider: str
    # Exact per-word timings when the engine provides them (edge-tts);
    # None for engines without word-boundary metadata.
    word_timings: Optional[List[WordTiming]] = None


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
