"""Video render endpoints (async background jobs)."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

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


@render_router.post("/render", response_model=RenderAccepted)
async def start_render(
    request: RenderRequest, background_tasks: BackgroundTasks
):
    """Queue a split-screen vertical video render as a background job."""
    if not compositor.ffmpeg_available():
        raise HTTPException(
            status_code=503,
            detail="ffmpeg binary not found on PATH; install ffmpeg to render.",
        )

    clip = gameplays.get_gameplay(request.gameplay_id)
    if clip is None:
        raise HTTPException(
            400, detail=f"Unknown gameplay_id '{request.gameplay_id}'"
        )
    if not clip.available:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Gameplay clip '{clip.id}' has no source file. "
                f"Place a {clip.id}.mp4 loop in server/assets/gameplay/."
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
