"""Azure Speech TTS provider (paid tier).

Azure Speech is the production-grade version of the neural voices that
edge-tts uses for free. Requires AZURE_SPEECH_KEY + AZURE_SPEECH_REGION.

If edge-tts cannot be used in your deployment (e.g. the free service gets
rate-limited), configure a real Azure Speech resource and this provider
kicks in with the identical voice IDs.
"""

from typing import List, Optional
from xml.sax.saxutils import escape

import httpx

from app.core import settings
from app.providers.tts.base import (
    BaseTTSProvider,
    SynthesizedAudio,
    Voice,
    split_emotion_segments,
    strip_emotion_tags,
)
from app.providers.tts.edge import _VOICE_SHORTLIST

# Inline delivery tags -> Azure `mstts:express-as` styles. Azure has no
# literal laugh/gasp style, so those map to the nearest documented one
# (cheerful laughter energy, fearful sharp intake). Voices that lack a
# style ignore it and speak with their default delivery.
_EMOTION_STYLES = {
    "whisper": "whispering",
    "laugh": "cheerful",
    "gasp": "fearful",
    "excited": "excited",
    "sigh": "disgruntled",
    "angry": "angry",
}


def build_ssml(text: str, voice: str, rate: str, pitch: str) -> str:
    """SSML document for one synthesis call, delivery tags included.

    Bracketed tags ([whisper], [angry], ...) become
    `<mstts:express-as style="...">` runs around the text they precede;
    untagged text passes through escaped. Tag-free input produces plain
    prosody-only SSML (no express-as element).
    """
    body_parts: List[str] = []
    for tag, chunk in split_emotion_segments(text):
        escaped = escape(chunk.strip())
        if not escaped:
            continue
        style = _EMOTION_STYLES.get(tag or "")
        if style:
            body_parts.append(
                f'<mstts:express-as style="{style}">{escaped}</mstts:express-as>'
            )
        else:
            body_parts.append(escaped)
    body = " ".join(body_parts) if body_parts else escape(strip_emotion_tags(text))
    return (
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" '
        'xml:lang="en-US">'
        f'<voice name="{escape(voice)}">'
        f'<prosody rate="{escape(rate)}" pitch="{escape(pitch)}">'
        f"{body}"
        "</prosody></voice></speak>"
    )


class AzureTTSProvider(BaseTTSProvider):
    name = "azure"
    OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

    def __init__(
        self,
        voice: Optional[str] = None,
        speech_key: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        super().__init__(voice or settings.DEFAULT_EDGE_VOICE)
        # Client-supplied credentials (studio key vault) take priority
        # over the server .env defaults.
        self.speech_key = (speech_key or settings.AZURE_SPEECH_KEY or "").strip()
        self.region = (region or settings.AZURE_SPEECH_REGION or "").strip()

    def is_configured(self) -> bool:
        return bool(self.speech_key and self.region)

    def _auth_token(self) -> str:
        """Azure Speech REST auth: signed JWT-like HMAC token (SCT)."""
        # Azure's documented flow for REST TTS uses an access token fetched
        # from the issueToken endpoint; use that (simpler + documented).
        url = (
            f"https://{self.region}.api.cognitive.microsoft.com"
            "/sts/v1.0/issueToken"
        )
        resp = httpx.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": self.speech_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.text

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        if not self.is_configured():
            raise RuntimeError(
                "Azure TTS requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION"
            )
        token = self._auth_token()
        ssml = build_ssml(text, self.voice, rate, pitch)
        url = (
            f"https://{self.region}.tts.speech.microsoft.com"
            f"/cognitiveservices/v1"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": self.OUTPUT_FORMAT,
            "User-Agent": "memeforge",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, content=ssml.encode("utf-8"), headers=headers)
            resp.raise_for_status()
        return SynthesizedAudio(
            audio_bytes=resp.content,
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    def list_voices(self) -> List[Voice]:
        return _VOICE_SHORTLIST
