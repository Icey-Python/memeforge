"""TikTok TTS provider (FREE, no API key) — LEGACY / best-effort.

Drives TikTok's internal text-to-speech service — the voices behind the
classic "TikTok voice" memes — via the same unauthenticated WXA endpoint
their in-app video editor uses. Returns mp3 audio.

No credentials are needed... in theory. In practice the unauthenticated
mirrors are increasingly unstable (404 / 403 / empty data for anonymous
clients), so this provider is now best-effort:

- Setting ``TIKTOK_SESSION_ID`` (or ``MEMEFORGE_TIKTOK_SESSION_ID``) in
  ``.env`` sends a logged-in ``sessionid`` cookie, which restores access
  on mirrors that reject anonymous traffic.
- When every mirror still fails, synthesis **automatically falls back**
  to Edge-TTS and then to the classic Brian voice (Meme Classic), so a
  flaky TikTok endpoint never kills the pipeline. The returned audio
  carries the provider that actually produced it.

For reliable free meme voices use the ``meme_classic`` (Brian & co.) or
``google`` providers instead; for production renders with an SLA prefer
``edge`` / ``azure`` / ``elevenlabs``. To force TikTok-only behavior,
self-host a WXA proxy worker and point ``MEMEFORGE_TIKTOK_TTS_URLS`` at
it — the automatic fallback only triggers when all mirrors fail.

Meme voice catalog (TikTok speaker ids):

- `en_us_002`         Jessie — the classic TikTok female voice
- `en_male_cody`      Serious Male (Cody) — deep, dramatic
- `en_male_narration` Narrator — documentary vibe
- `en_us_ghostface`   Ghostface (Scream)
- `en_us_trickster`   Trickster — chaotic gremlin energy

The endpoint ignores rate/pitch (accepted for API compatibility).
"""

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core import settings
from app.providers.tts.base import (
    BaseTTSProvider,
    SynthesizedAudio,
    Voice,
    chunk_text,
)
from app.providers.tts.edge import EdgeTTSProvider
from app.providers.tts.meme_classic import MemeClassicTTSProvider

# Re-exported for callers/tests that import chunk_text from this module.
__all__ = ["TikTokTTSProvider", "chunk_text"]

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
        try:
            audio = b"".join([await self._synthesize_chunk(c) for c in chunks])
            return SynthesizedAudio(
                audio_bytes=audio,
                format="mp3",
                voice=self.voice,
                provider=self.name,
            )
        except Exception as exc:  # noqa: BLE001 - degrade, don't fail the render
            return await self._fallback_synthesize(text, rate, pitch, cause=exc)

    async def _fallback_synthesize(
        self, text: str, rate: str, pitch: str, cause: Exception
    ) -> SynthesizedAudio:
        """Keep the pipeline alive when every TikTok mirror is down.

        The WXA mirrors are unofficial and frequently reject anonymous
        traffic (403/404), so failed TikTok synthesis degrades to free
        alternatives instead of failing the render: Edge-TTS first (neural,
        rate/pitch aware), then the iconic Brian voice. The returned audio
        carries the provider that actually produced it.
        """
        logging.getLogger("memeforge").warning(
            "TikTok TTS failed (voice %s): %s — falling back to edge-tts "
            "then Brian (meme_classic)",
            self.voice,
            cause,
        )
        for fallback_cls in (EdgeTTSProvider, MemeClassicTTSProvider):
            try:
                provider = fallback_cls()  # provider default voice
                return await provider.synthesize(text, rate=rate, pitch=pitch)
            except Exception:  # noqa: BLE001 - try the next fallback
                continue
        raise RuntimeError(
            f"TikTok TTS failed for voice {self.voice} and both free "
            f"fallbacks (edge-tts, meme_classic) failed too. "
            f"Original error: {cause}"
        )

    def _session_cookies(self) -> Optional[Dict[str, str]]:
        """Logged-in session cookie, when TIKTOK_SESSION_ID is configured.

        Anonymous WXA calls are often 403-rejected; a valid `sessionid`
        cookie (from a logged-in tiktok.com browser session) restores
        access on those mirrors.
        """
        session_id = (settings.TIKTOK_SESSION_ID or "").strip()
        return {"sessionid": session_id} if session_id else None

    async def _synthesize_chunk(self, text: str) -> bytes:
        """POST one text chunk to the WXA endpoint, trying mirror fallbacks."""
        payload = {"text": text, "speaker": self.voice}
        cookies = self._session_cookies()
        last_exc: Optional[Exception] = None
        for url in self._endpoints():
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        url, json=payload, headers=_HEADERS, cookies=cookies
                    )
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
