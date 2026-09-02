"""Main API router: health + /api/v1 namespace."""

from fastapi import APIRouter

from app.api.endpoints.health import health_router
from app.api.endpoints.render import render_router
from app.api.endpoints.script import script_router
from app.api.endpoints.tts import tts_router
from app.core.settings import API_V1_PREFIX

router = APIRouter()


@router.get("/")
async def root():
    return {
        "msg": "Memeforge API is running",
        "docs": "/docs",
        "api": API_V1_PREFIX,
    }


# Health is mounted at root level (no /api prefix) for container probes.
router.include_router(health_router)

# Everything else lives under /api/v1 (matches the Next.js apiBase).
router.include_router(script_router, prefix=API_V1_PREFIX)
router.include_router(tts_router, prefix=API_V1_PREFIX)
router.include_router(render_router, prefix=API_V1_PREFIX)
