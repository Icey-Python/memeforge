"""Video render endpoints (async background jobs)."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core import settings
from app.schemas.render_schema import (
    JobStatus,
    RenderAccepted,
    RenderJob,
    RenderRequest,
)
from app.services import jobs as jobs_service
from app.services.rendering import compositor, renderer
from app.utils import gameplays

render_router = APIRouter()


@render_router.get("/render/gameplays")
async def list_gameplay_clips():
    """Gameplay loop catalog for the frontend gameplay node."""
    return [clip.model_dump() for clip in gameplays.list_gameplays()]


def _validate_stock_clips(request: RenderRequest) -> None:
    """Stock-clip payload guards (count + provider allowlist)."""
    if len(request.stock_clips) > settings.STOCK_MAX_CLIPS:
        raise HTTPException(
            400,
            detail=(
                f"Too many stock clips ({len(request.stock_clips)}); "
                f"the limit is {settings.STOCK_MAX_CLIPS}."
            ),
        )
    valid_providers = {"pexels", "pixabay"}
    for clip in request.stock_clips:
        if clip.provider not in valid_providers:
            raise HTTPException(
                400,
                detail=(
                    f"Unknown stock provider '{clip.provider}' "
                    f"(expected one of {sorted(valid_providers)})."
                ),
            )


@render_router.post("/render", response_model=RenderAccepted)
async def start_render(
    request: RenderRequest, background_tasks: BackgroundTasks
):
    """Queue a full-screen vertical video render as a background job.

    Background source: preset gameplay loop (`gameplay_id`) OR a list
    of picked stock clips (`stock_clips`, Pexels / Pixabay) that get
    stitched into one continuous background.
    """
    if not compositor.ffmpeg_available():
        raise HTTPException(
            status_code=503,
            detail="ffmpeg binary not found on PATH; install ffmpeg to render.",
        )

    if request.stock_clips:
        _validate_stock_clips(request)
    elif request.gameplay_id:
        clip = gameplays.get_gameplay(request.gameplay_id)
        if clip is None:
            raise HTTPException(
                400, detail=f"Unknown gameplay_id '{request.gameplay_id}'"
            )
        if not clip.available:
            raise HTTPException(
                409,
                detail=(
                    f"Gameplay clip '{clip.id}' has no source file. "
                    f"Place a {clip.id}.mp4 loop in server/assets/gameplay/."
                ),
            )
    else:
        raise HTTPException(
            400,
            detail=(
                "No background source: set gameplay_id (preset loop) or "
                "stock_clips (Pexels / Pixabay picks)."
            ),
        )

    job = jobs_service.job_store.create()
    background_tasks.add_task(renderer.run_render_job, job.job_id, request)
    return RenderAccepted(
        job_id=job.job_id,
        status=job.status,
        status_url=f"/api/v1/render/{job.job_id}",
    )


@render_router.get("/render", response_model=list[RenderJob])
async def list_render_jobs():
    """Recent render jobs (debug/monitoring)."""
    return jobs_service.job_store.list()


@render_router.get("/render/{job_id}", response_model=RenderJob)
async def get_render_job(job_id: str):
    """Poll a render job's status; completed jobs carry a video_url."""
    job = jobs_service.job_store.get(job_id)
    if job is None:
        raise HTTPException(404, detail=f"Unknown render job '{job_id}'")
    return job
