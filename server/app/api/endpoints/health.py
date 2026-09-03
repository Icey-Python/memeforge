"""Health check endpoint."""

from fastapi import APIRouter

from app.core import settings
from app.providers.stock import registry as stock_registry
from app.providers.tts.edge import EdgeTTSProvider
from app.services.rendering import compositor

health_router = APIRouter(tags=["health"])


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
            "stock_pexels": stock.get("pexels", False),
            "stock_pixabay": stock.get("pixabay", False),
        },
    }
