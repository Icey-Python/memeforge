"""Health check endpoint."""

from fastapi import APIRouter

from app.core import settings
from app.providers.stock import registry as stock_registry
from app.providers.tts.edge import EdgeTTSProvider
from app.services.rendering import compositor

health_router = APIRouter(tags=["health"])


def _key_capabilities() -> dict:
    """Which server-side credential defaults are configured (.env).

    The studio settings drawer uses these booleans to show "Using Server
    Default" vs "Not configured" for each key field (client vault keys
    are resolved in the browser and never sent here).
    """
    return {
        "llm_openai": bool(settings.OPENAI_API_KEY),
        "llm_openrouter": bool(settings.OPENROUTER_API_KEY),
        "llm_groq": bool(settings.GROQ_API_KEY),
        "llm_anthropic": bool(settings.ANTHROPIC_API_KEY),
        "tts_elevenlabs": bool(settings.ELEVENLABS_API_KEY),
        "tts_azure": bool(settings.AZURE_SPEECH_KEY),
        "tts_azure_region": bool(settings.AZURE_SPEECH_REGION),
    }


@health_router.get("/health")
async def health_check():
    """Liveness + capability report (ffmpeg, edge-tts, stock keys)."""
    stock = {p.name: p.is_configured() for p in stock_registry.get_stock_providers()}
    return {
        "status": "ok",
        "app": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "capabilities": {
            "ffmpeg": compositor.ffmpeg_available(),
            "ffprobe": compositor.ffprobe_available(),
            "edge_tts": EdgeTTSProvider().is_configured(),
            **_key_capabilities(),
            "stock_pexels": stock.get("pexels", False),
            "stock_pixabay": stock.get("pixabay", False),
        },
    }
