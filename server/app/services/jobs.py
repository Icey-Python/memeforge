"""In-memory async render job registry.

Tracks background video render jobs started via FastAPI's BackgroundTasks.
Jobs live for the lifetime of the process — swap for Redis/Postgres when
you need durability across restarts (interface stays the same).
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.schemas.render_schema import JobStatus, RenderJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RenderJobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, RenderJob] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._order: List[str] = []

    def create(self) -> RenderJob:
        job_id = uuid.uuid4().hex[:12]
        job = RenderJob(
            job_id=job_id,
            status=JobStatus.queued,
            progress=0.0,
            message="Queued",
            created_at=_now(),
            updated_at=_now(),
        )
        self._jobs[job_id] = job
        self._order.append(job_id)
        return job

    def get(self, job_id: str) -> Optional[RenderJob]:
        return self._jobs.get(job_id)

    def lock(self, job_id: str) -> asyncio.Lock:
        if job_id not in self._locks:
            self._locks[job_id] = asyncio.Lock()
        return self._locks[job_id]

    def update(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        video_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[RenderJob]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if video_url is not None:
            job.video_url = video_url
        if error is not None:
            job.error = error
        job.updated_at = _now()
        return job

    def list(self) -> List[RenderJob]:
        return [self._jobs[jid] for jid in self._order if jid in self._jobs]


# Singleton used by the render endpoints.
job_store = RenderJobStore()
