"""Edge-TTS provider (FREE, no API key).

Uses the `edge-tts` package which drives Microsoft Edge's online
text-to-speech service — the same neural voices as Azure Speech, at no
cost. This is memeforge's default voiceover engine.

Docs: https://github.com/rany2/edge-tts
"""

from typing import List, Optional

from app.core import settings
from app.providers.tts.base import BaseTTSProvider, SynthesizedAudio, Voice

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

        communicate = edge_tts.Communicate(
            text=text, voice=self.voice, rate=rate, pitch=pitch
        )
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        if not chunks:
            raise RuntimeError(f"edge-tts produced no audio for voice {self.voice}")
        return SynthesizedAudio(
            audio_bytes=b"".join(chunks),
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    def list_voices(self) -> List[Voice]:
        return _VOICE_SHORTLIST
