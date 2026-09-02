"""Google Translate TTS provider (FREE, no API key).

High-reliability fallback engine: Google's public ``translate_tts``
endpoint (the audio behind the translate widget) is one of the most
stable free TTS sources on the internet::

    GET https://translate.google.com/translate_tts
        ?ie=UTF-8&q={text}&tl={lang}&client=tw-ob

The endpoint hard-caps request text length (~200 chars); longer texts
are split into chunks and the mp3 frames are concatenated. There is no
voice selection beyond language/accent — the voice id maps to the
``tl`` parameter (``en`` is the default US English speaker).

The endpoint ignores rate/pitch (accepted for API compatibility).
"""

import asyncio
from typing import List, Optional

import httpx

from app.core import settings
from app.providers.tts.base import (
    BaseTTSProvider,
    SynthesizedAudio,
    Voice,
    chunk_text,
)

_BASE_URL = "https://translate.google.com/translate_tts"

# Google 403s requests without a browser user-agent.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://translate.google.com/",
}

# The endpoint rejects requests over ~200 chars with HTTP 400.
_MAX_TEXT_LEN = 200

# Small politeness gap between chunk requests (rapid-fire calls get
# throttled by Google's edge).
_INTER_CHUNK_DELAY_S = 0.15

VOICE_CATALOG: List[Voice] = [
    Voice(
        id="en",
        label="Google US English — reliability fallback",
        language="en-US",
        gender="female",
        tags=["fallback"],
    ),
    Voice(
        id="en-GB",
        label="Google UK English",
        language="en-GB",
        gender="female",
        tags=["fallback"],
    ),
    Voice(
        id="en-AU",
        label="Google Australian English",
        language="en-AU",
        gender="female",
        tags=["fallback"],
    ),
    Voice(
        id="en-IN",
        label="Google Indian English",
        language="en-IN",
        gender="female",
        tags=["fallback"],
    ),
]


class GoogleTTSProvider(BaseTTSProvider):
    name = "google"

    def __init__(self, voice: Optional[str] = None) -> None:
        super().__init__(voice or settings.DEFAULT_GOOGLE_TTS_VOICE)

    def is_configured(self) -> bool:
        return True  # free, keyless endpoint

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        # rate/pitch are accepted for BaseTTSProvider compatibility but the
        # upstream endpoint does not expose them.
        chunks = chunk_text(text, limit=_MAX_TEXT_LEN)
        if not chunks:
            raise ValueError("Google TTS got empty text")
        parts: List[bytes] = []
        for i, chunk in enumerate(chunks):
            if i:
                await asyncio.sleep(_INTER_CHUNK_DELAY_S)
            parts.append(await self._synthesize_chunk(chunk))
        return SynthesizedAudio(
            audio_bytes=b"".join(parts),
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    async def _synthesize_chunk(self, text: str) -> bytes:
        """GET one text chunk from the translate_tts endpoint."""
        params = {
            "ie": "UTF-8",
            "q": text,
            "tl": self.voice,
            "client": "tw-ob",
        }
        async with httpx.AsyncClient(
            timeout=60.0, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(_BASE_URL, params=params)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Google translate_tts returned HTTP {resp.status_code}"
            )
        if not resp.content:
            raise RuntimeError("Google translate_tts returned empty audio")
        return resp.content

    def list_voices(self) -> List[Voice]:
        return [v.model_copy() for v in VOICE_CATALOG]
