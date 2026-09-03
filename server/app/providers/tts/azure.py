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
from app.providers.tts.base import BaseTTSProvider, SynthesizedAudio, Voice
from app.providers.tts.edge import _VOICE_SHORTLIST


class AzureTTSProvider(BaseTTSProvider):
    name = "azure"
    OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

    def __init__(
        self,
        voice: Optional[str] = None,
        api_key: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        super().__init__(voice or settings.DEFAULT_EDGE_VOICE)
        # Per-request overrides (studio key fields) win over the server .env.
        self.api_key = api_key or settings.AZURE_SPEECH_KEY
        self.region = region or settings.AZURE_SPEECH_REGION

    def is_configured(self) -> bool:
        return bool(self.api_key and self.region)

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
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
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
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xml:lang="en-US">'
            f'<voice name="{escape(self.voice)}">'
            f'<prosody rate="{escape(rate)}" pitch="{escape(pitch)}">'
            f"{escape(text)}"
            "</prosody></voice></speak>"
        )
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
