"""TikTok TTS provider (FREE, no API key).

Drives TikTok's internal text-to-speech service — the voices behind the
classic "TikTok voice" memes — via the same unauthenticated WXA endpoint
their in-app video editor uses. Returns mp3 audio.

No credentials are needed, which makes this perfect for meme drafting.
It is an unofficial endpoint though: it can be rate-limited, regional, or
change without notice (the mirrors occasionally answer 404 for a while),
so for production renders with an SLA prefer `edge` / `azure` /
`elevenlabs`. If every mirror fails, self-host a WXA proxy worker and
point `MEMEFORGE_TIKTOK_TTS_URLS` at it.

Meme voice catalog (TikTok speaker ids):

- `en_us_002`         Jessie — the classic TikTok female voice
- `en_male_cody`      Serious Male (Cody) — deep, dramatic
- `en_male_narration` Narrator — documentary vibe
- `en_us_ghostface`   Ghostface (Scream)
- `en_us_trickster`   Trickster — chaotic gremlin energy

The endpoint ignores rate/pitch (accepted for API compatibility).
"""

import base64
from typing import Any, List, Optional

import httpx

from app.core import settings
from app.providers.tts.base import BaseTTSProvider, SynthesizedAudio, Voice

# Known mirrors of the WXA endpoint; the first is tried, then fallbacks.
_DEFAULT_ENDPOINTS = [
    "https://api16-normal-v6.tiktokv.com/16/api/v1/wxa/tts",
    "https://api16-normal-c-useast1a.tiktokv.com/16/api/v1/wxa/tts",
    "https://api22-normal-c-useast2a.tiktokv.com/16/api/v1/wxa/tts",
    "https://api19-normal-c-useast1a.tiktokv.com/16/api/v1/wxa/tts",
]

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 13)",
}

# The endpoint hard-caps request text length (~300 chars); longer texts
# are split into chunks and the mp3 frames are concatenated.
_MAX_TEXT_LEN = 280

VOICE_CATALOG: List[Voice] = [
    Voice(
        id="en_us_002",
        label="Jessie — classic TikTok voice",
        language="en-US",
        gender="female",
        tags=["meme"],
    ),
    Voice(
        id="en_male_cody",
        label="Serious Male (Cody)",
        language="en-US",
        gender="male",
        tags=["meme", "narration"],
    ),
    Voice(
        id="en_male_narration",
        label="Narrator",
        language="en-US",
        gender="male",
        tags=["meme", "narration"],
    ),
    Voice(
        id="en_us_ghostface",
        label="Ghostface (Scream)",
        language="en-US",
        gender="male",
        tags=["meme"],
    ),
    Voice(
        id="en_us_trickster",
        label="Trickster",
        language="en-US",
        gender="male",
        tags=["meme"],
    ),
]


def chunk_text(text: str, limit: int = _MAX_TEXT_LEN) -> List[str]:
    """Split text into endpoint-sized chunks (on word boundaries)."""
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


class TikTokTTSProvider(BaseTTSProvider):
    name = "tiktok"

    def __init__(self, voice: Optional[str] = None) -> None:
        super().__init__(voice or settings.DEFAULT_TIKTOK_VOICE)

    def is_configured(self) -> bool:
        return True  # free, keyless endpoint

    def _endpoints(self) -> List[str]:
        if settings.TIKTOK_TTS_URLS:
            return [u.strip() for u in settings.TIKTOK_TTS_URLS.split(",") if u.strip()]
        return list(_DEFAULT_ENDPOINTS)

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        # rate/pitch are accepted for BaseTTSProvider compatibility but the
        # upstream endpoint does not expose them.
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("TikTok TTS got empty text")
        audio = b"".join([await self._synthesize_chunk(c) for c in chunks])
        return SynthesizedAudio(
            audio_bytes=audio,
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    async def _synthesize_chunk(self, text: str) -> bytes:
        """POST one text chunk to the WXA endpoint, trying mirror fallbacks."""
        payload = {"text": text, "speaker": self.voice}
        last_exc: Optional[Exception] = None
        for url in self._endpoints():
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, json=payload, headers=_HEADERS)
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"TikTok TTS endpoint returned HTTP {resp.status_code}"
                    )
                return self._extract_audio(resp.json())
            except Exception as exc:  # noqa: BLE001 - try the next mirror
                last_exc = exc
        raise RuntimeError(f"TikTok TTS failed for voice {self.voice}: {last_exc}")

    @staticmethod
    def _extract_audio(payload: Any) -> bytes:
        """Decode the WXA JSON response into mp3 bytes.

        Success shape: `{"status_code": 0, "data": "<base64 mp3>"}`
        (some mirrors return `data` as a list of base64 strings).
        """
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected TikTok TTS response: {payload!r}")
        status = payload.get("status_code")
        if status not in (0, "0"):
            raise RuntimeError(
                f"TikTok TTS error {status}: "
                f"{payload.get('status_msg') or payload}"
            )
        data = payload.get("data") or ""
        if isinstance(data, list):
            data = "".join(str(part) for part in data)
        if not data:
            raise RuntimeError("TikTok TTS returned empty audio data")
        return base64.b64decode(data)

    def list_voices(self) -> List[Voice]:
        return [v.model_copy() for v in VOICE_CATALOG]
