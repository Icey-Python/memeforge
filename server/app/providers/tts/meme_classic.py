"""Meme Classic TTS provider (FREE, no API key) — the iconic meme voices.

Drives ttsmp3.com's free ``makemp3_new.php`` API, which fronts the
classic AWS Polly voice cast behind every Twitch-chat TTS bot and
countless viral TTS videos:

- ``Brian``   — British English male. THE meme TTS voice.
- ``Justin``  — US child/teen. The classic kid-story narrator.
- ``Matthew`` — US male, deep and serious. Meme documentary narrator.
- ``Kendra`` / ``Salli`` / ``Joey`` / ``Ivy`` / ``Joanna`` — the rest of
  the classic cast (news anchors, calm narrators, kid voices).

Flow: a form POST (``msg``, ``lang=<voice>``, ``source=ttsmp3``) returns
JSON pointing at a hosted MP3 (``{"Error": 0, "URL": "...", "MP3": "..."}``);
the MP3 is then downloaded and returned as bytes. Free, fast, keyless,
no rate limits.

The endpoint ignores rate/pitch (accepted for API compatibility).
"""

from typing import Any, List, Optional

import httpx

from app.core import settings
from app.providers.tts.base import (
    BaseTTSProvider,
    SynthesizedAudio,
    Voice,
    chunk_text,
)

_API_URL = "https://ttsmp3.com/makemp3_new.php"
_DOWNLOAD_BASE = "https://ttsmp3.com/created_mp3"

# Browser-like headers: the endpoint 403s plain script user-agents.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://ttsmp3.com/",
    "Origin": "https://ttsmp3.com",
}

# Single-request safety cap; the site accepts a few thousand chars per
# call, longer scripts are chunked and the mp3 frames concatenated.
_MAX_TEXT_LEN = 3000

VOICE_CATALOG: List[Voice] = [
    Voice(
        id="Brian",
        label="Brian — iconic meme voice (British)",
        language="en-GB",
        gender="male",
        tags=["meme", "iconic"],
    ),
    Voice(
        id="Justin",
        label="Justin — kid/teen story voice",
        language="en-US",
        gender="male",
        tags=["meme", "kid"],
    ),
    Voice(
        id="Matthew",
        label="Matthew — deep serious narrator",
        language="en-US",
        gender="male",
        tags=["meme", "narration"],
    ),
    Voice(
        id="Kendra",
        label="Kendra",
        language="en-US",
        gender="female",
        tags=["meme"],
    ),
    Voice(
        id="Salli",
        label="Salli",
        language="en-US",
        gender="female",
        tags=["meme"],
    ),
    Voice(
        id="Joey",
        label="Joey",
        language="en-US",
        gender="male",
        tags=["meme"],
    ),
    Voice(
        id="Ivy",
        label="Ivy — kid voice",
        language="en-US",
        gender="female",
        tags=["meme", "kid"],
    ),
    Voice(
        id="Joanna",
        label="Joanna",
        language="en-US",
        gender="female",
        tags=["meme", "narration"],
    ),
]


class MemeClassicTTSProvider(BaseTTSProvider):
    name = "meme_classic"

    def __init__(self, voice: Optional[str] = None) -> None:
        super().__init__(voice or settings.DEFAULT_MEME_CLASSIC_VOICE)

    def is_configured(self) -> bool:
        return True  # free, keyless endpoint

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        # rate/pitch are accepted for BaseTTSProvider compatibility but the
        # upstream endpoint does not expose them.
        chunks = chunk_text(text, limit=_MAX_TEXT_LEN)
        if not chunks:
            raise ValueError("Meme Classic TTS got empty text")
        audio = b"".join([await self._synthesize_chunk(c) for c in chunks])
        return SynthesizedAudio(
            audio_bytes=audio,
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    async def _synthesize_chunk(self, text: str) -> bytes:
        """POST one text chunk, then download the resulting MP3."""
        async with httpx.AsyncClient(
            timeout=60.0, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.post(
                _API_URL,
                data={"msg": text, "lang": self.voice, "source": "ttsmp3"},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"ttsmp3 endpoint returned HTTP {resp.status_code}"
                )
            mp3_url = self._extract_mp3_url(resp.json())
            mp3 = await client.get(mp3_url)
        if mp3.status_code != 200:
            raise RuntimeError(
                f"ttsmp3 MP3 download returned HTTP {mp3.status_code}"
            )
        if not mp3.content:
            raise RuntimeError("ttsmp3 returned an empty MP3")
        return mp3.content

    @staticmethod
    def _extract_mp3_url(payload: Any) -> str:
        """Decode the makemp3_new.php JSON response into an MP3 URL.

        Success shape::

            {"Error": 0, "Speaker": "Brian", "Text": "...",
             "URL": "https://ttsmp3.com/created_mp3/<hash>.mp3",
             "MP3": "<hash>.mp3", "success": 1}

        ``URL`` is absolute when present; older shapes only carry the
        ``MP3`` basename, which resolves against the created_mp3 folder.
        """
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected ttsmp3 response: {payload!r}")
        error = payload.get("Error")
        if error not in (0, "0", None):
            raise RuntimeError(f"ttsmp3 error {error}: {payload}")
        url = payload.get("URL")
        if isinstance(url, str) and url:
            return url
        name = payload.get("MP3")
        if isinstance(name, str) and name:
            return f"{_DOWNLOAD_BASE}/{name}"
        raise RuntimeError(f"ttsmp3 response missing MP3 URL: {payload!r}")

    def list_voices(self) -> List[Voice]:
        return [v.model_copy() for v in VOICE_CATALOG]
