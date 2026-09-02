"""TTS endpoints (voiceover connectors)."""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core import settings
from app.providers.tts import registry as tts_registry
from app.schemas.render_schema import TTSProvider, TTSRequest, TTSResponse

tts_router = APIRouter()


@tts_router.get("/voices")
async def list_voices(provider: TTSProvider = TTSProvider.edge):
    """Voice catalog for the frontend voiceover node voice picker."""
    try:
        voices = await tts_registry.list_tts_voices(provider.value)
    except Exception as exc:
        raise HTTPException(502, detail=f"Voice listing failed: {exc}") from exc
    return [
        {
            "id": v.id,
            "label": v.label,
            "language": v.language,
            "gender": v.gender,
        }
        for v in voices
    ]


@tts_router.post("/tts", response_model=TTSResponse)
async def synthesize_speech(request: TTSRequest):
    """Synthesize speech; returns a URL to the generated audio file."""
    provider = tts_registry.get_tts_provider(
        request.provider.value, voice=request.voice
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
