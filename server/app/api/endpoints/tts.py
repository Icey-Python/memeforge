"""TTS endpoints (voiceover connectors)."""

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.core import settings
from app.providers.tts import registry as tts_registry
from app.schemas.render_schema import TTSProvider, TTSRequest, TTSResponse


def _client_tts_credentials(
    elevenlabs_key_header: Optional[str],
    azure_key_header: Optional[str],
    azure_region_header: Optional[str],
    elevenlabs_key_query: Optional[str],
    azure_key_query: Optional[str],
    azure_region_query: Optional[str],
) -> dict:
    """Merge client-supplied TTS credentials (headers win over query).

    GET endpoints cannot carry a body, so the studio sends its vault keys
    either as X-... headers or query params; both are accepted here.
    """
    return {
        "elevenlabs_api_key": elevenlabs_key_header or elevenlabs_key_query or None,
        "azure_speech_key": azure_key_header or azure_key_query or None,
        "azure_speech_region": (
            azure_region_header or azure_region_query or None
        ),
    }


tts_router = APIRouter()


@tts_router.get("/voices")
async def list_voices(
    provider: TTSProvider = TTSProvider.edge,
    elevenlabs_api_key: Optional[str] = Query(
        default=None, description="ElevenLabs API key override (studio key vault)"
    ),
    azure_speech_key: Optional[str] = Query(
        default=None, description="Azure Speech key override (studio key vault)"
    ),
    azure_speech_region: Optional[str] = Query(
        default=None, description="Azure Speech region override"
    ),
    x_elevenlabs_key: Optional[str] = Header(
        default=None, alias="X-Elevenlabs-Key"
    ),
    x_azure_key: Optional[str] = Header(default=None, alias="X-Azure-Key"),
    x_azure_region: Optional[str] = Header(default=None, alias="X-Azure-Region"),
):
    """Voice catalog for the frontend voiceover node voice picker.

    Voices carry `tags` (e.g. "meme") so the studio can group them into
    categories like "TikTok Meme Voices" or "Popular meme neural voices".
    Client-supplied credentials (headers or query params) take priority
    over the server .env — this is what lets ElevenLabs list the account's
    voice library with a vault key.
    """
    creds = _client_tts_credentials(
        x_elevenlabs_key,
        x_azure_key,
        x_azure_region,
        elevenlabs_api_key,
        azure_speech_key,
        azure_speech_region,
    )
    try:
        voices = await tts_registry.list_tts_voices(provider.value, **creds)
    except Exception as exc:
        raise HTTPException(502, detail=f"Voice listing failed: {exc}") from exc
    return [
        {
            "id": v.id,
            "label": v.label,
            "language": v.language,
            "gender": v.gender,
            "tags": v.tags,
        }
        for v in voices
    ]


@tts_router.post("/tts", response_model=TTSResponse)
async def synthesize_speech(request: TTSRequest):
    """Synthesize speech; returns a URL to the generated audio file.

    Client-supplied credentials in the request body (studio key vault)
    take priority over the server .env.
    """
    provider = tts_registry.get_tts_provider(
        request.provider.value,
        voice=request.voice,
        elevenlabs_api_key=request.elevenlabs_api_key,
        azure_speech_key=request.azure_speech_key,
        azure_speech_region=request.azure_speech_region,
    )
    if not provider.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                f"TTS provider '{provider.name}' is not configured "
                "(missing credentials or package)."
            ),
        )
    try:
        audio = await provider.synthesize(
            text=request.text, rate=request.rate, pitch=request.pitch
        )
    except Exception as exc:
        raise HTTPException(502, detail=f"TTS synthesis failed: {exc}") from exc

    audio_path = settings.OUTPUT_DIR / f"tts-{uuid.uuid4().hex[:10]}.{audio.format}"
    audio_path.write_bytes(audio.audio_bytes)

    return TTSResponse(
        provider=audio.provider,
        voice=audio.voice,
        audio_url=f"/outputs/{audio_path.name}",
    )


@tts_router.get("/tts/{filename}")
async def get_tts_audio(filename: str):
    """Serve a previously generated TTS audio file (also under /outputs)."""
    path = settings.OUTPUT_DIR / filename
    if not path.is_file() or path.parent != settings.OUTPUT_DIR:
        raise HTTPException(404, detail="Audio not found")
    return FileResponse(path)
