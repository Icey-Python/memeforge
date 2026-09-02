"""Edge-TTS provider (FREE, no API key).

Uses the `edge-tts` package which drives Microsoft Edge's online
text-to-speech service — the same neural voices as Azure Speech, at no
cost. This is memeforge's default voiceover engine.

Word-boundary metadata: the service can emit an exact start/end
interval for every spoken word (`BoundaryType.Word` events). Those
timestamps drive frame-accurate kinetic captions downstream, so
synthesis requests them and the timings ride along on
`SynthesizedAudio.word_timings`.

Docs: https://github.com/rany2/edge-tts
"""

import re
from typing import List, Optional

from app.core import settings
from app.providers.tts.base import (
    BaseTTSProvider,
    SynthesizedAudio,
    Voice,
    WordTiming,
)

# Curated shortlist; the full catalog has 300+ voices and can be listed
# with `edge-tts --list-voices`. Popular meme neural voices carry the
# "meme" tag so the studio UI can pre-categorize them.
_VOICE_SHORTLIST: List[Voice] = [
    Voice(id="en-US-ChristopherNeural", label="Christopher", language="en-US", gender="male", tags=["meme", "narration"]),
    Voice(id="en-US-GuyNeural", label="Guy", language="en-US", gender="male", tags=["meme", "energetic"]),
    Voice(id="en-US-EricNeural", label="Eric", language="en-US", gender="male", tags=["meme", "casual"]),
    Voice(id="en-US-JennyNeural", label="Jenny", language="en-US", gender="female", tags=["meme", "narration"]),
    Voice(id="en-US-RogerNeural", label="Roger", language="en-US", gender="male", tags=["deadpan"]),
    Voice(id="en-US-MichelleNeural", label="Michelle", language="en-US", gender="female", tags=["casual"]),
    Voice(id="en-GB-RyanNeural", label="Ryan", language="en-GB", gender="male", tags=["meme"]),
    Voice(id="en-GB-SoniaNeural", label="Sonia", language="en-GB", gender="female", tags=["narration"]),
    Voice(id="en-AU-NatashaNeural", label="Natasha", language="en-AU", gender="female", tags=["casual"]),
    Voice(id="en-IE-EmilyNeural", label="Emily", language="en-IE", gender="female", tags=["deadpan"]),
]


# Edge-TTS stream metadata offsets/durations are in 100-nanosecond ticks.
_TICKS_PER_SECOND = 10_000_000


def _word_timings_from_stream(chunks: List[dict]) -> List[WordTiming]:
    """Convert WordBoundary stream events into second-based timings.

    Punctuation-only boundary events (text without any word character)
    are dropped so the remaining timings line up positionally with the
    words of the source text.
    """
    timings: List[WordTiming] = []
    for chunk in chunks:
        if chunk.get("type") != "WordBoundary":
            continue
        text = str(chunk.get("text", ""))
        if not re.search(r"\w", text):
            continue  # punctuation-only boundary (",", ".", "…")
        start = float(chunk.get("offset", 0)) / _TICKS_PER_SECOND
        end = start + float(chunk.get("duration", 0)) / _TICKS_PER_SECOND
        if end > start:
            timings.append(WordTiming(text=text, start=start, end=end))
    return timings


class EdgeTTSProvider(BaseTTSProvider):
    name = "edge"

    def __init__(self, voice: Optional[str] = None) -> None:
        super().__init__(voice or settings.DEFAULT_EDGE_VOICE)

    def is_configured(self) -> bool:
        try:
            import edge_tts  # noqa: F401

            return True
        except ImportError:
            return False

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError(
                "edge-tts is not installed; run `pip install edge-tts`"
            ) from exc

        # Ask the service for per-word boundary metadata (exact start/end
        # for every spoken word). Older edge-tts releases without the
        # `boundary` kwarg still surface WordBoundary events by default.
        try:
            communicate = edge_tts.Communicate(
                text=text, voice=self.voice, rate=rate, pitch=pitch,
                boundary="WordBoundary",
            )
        except TypeError:
            communicate = edge_tts.Communicate(
                text=text, voice=self.voice, rate=rate, pitch=pitch
            )
        audio_chunks = []
        meta_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            else:
                meta_chunks.append(chunk)
        if not audio_chunks:
            raise RuntimeError(f"edge-tts produced no audio for voice {self.voice}")
        word_timings = _word_timings_from_stream(meta_chunks)
        return SynthesizedAudio(
            audio_bytes=b"".join(audio_chunks),
            format="mp3",
            voice=self.voice,
            provider=self.name,
            word_timings=word_timings or None,
        )

    def list_voices(self) -> List[Voice]:
        return _VOICE_SHORTLIST
