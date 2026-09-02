"""Render orchestrator.

Runs a full pipeline as a background job:

    script lines ──▶ TTS per line ──▶ concat voiceover ──▶ ffmpeg compositor ──▶ mp4
        │                                                        ▲
        ├──▶ kinetic caption timeline ──────────────────────────┘
        └──▶ Reddit-style card (Pillow) ──▶ top frame

The job store tracks progress; the frontend Preview & Export node polls
`GET /api/v1/render/{job_id}` until status is completed/failed.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

from app.core import settings
from app.schemas.render_schema import JobStatus, RenderRequest
from app.services import jobs as jobs_service
from app.services.rendering import compositor
from app.services.rendering.captions import build_caption_timeline

# Fallback speech rate when TTS duration probing is unavailable.
_SECONDS_PER_WORD = 0.42
_LINE_TAIL_SECONDS = 0.35

# Per-line TTS hardening: network TTS can stall on a bad chunk; a hung
# stream must never hang the whole render job.
_TTS_LINE_TIMEOUT_S = 60.0
_TTS_ATTEMPTS = 3


async def _synthesize_with_retry(provider, text: str):
    """Synthesize one line with timeout + retries."""
    last_exc: Exception | None = None
    for attempt in range(1, _TTS_ATTEMPTS + 1):
        try:
            return await asyncio.wait_for(
                provider.synthesize(text), timeout=_TTS_LINE_TIMEOUT_S
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - retry any TTS failure
            last_exc = exc
            if attempt < _TTS_ATTEMPTS:
                await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(
        f"TTS failed after {_TTS_ATTEMPTS} attempts: {last_exc}"
    )


def _find_sfx() -> Optional[Path]:
    """First punchline SFX dropped into assets/sfx/ (any audio format)."""
    if not settings.SFX_DIR.exists():
        return None
    for candidate in sorted(settings.SFX_DIR.iterdir()):
        if candidate.suffix.lower() in {".mp3", ".wav", ".ogg", ".m4a", ".aac"}:
            return candidate
    return None


async def run_render_job(job_id: str, request: RenderRequest) -> None:
    """Execute a render job; updates the job store as it progresses."""
    store = jobs_service.job_store
    store.update(job_id, status=JobStatus.running, progress=0.05,
                 message="Starting render")

    workdir = Path(tempfile.mkdtemp(prefix=f"render-{job_id}-"))
    try:
        # --- 1. Gameplay loop ------------------------------------------------
        gameplay = None
        from app.utils import gameplays as gameplays_util

        clip = gameplays_util.get_gameplay(request.gameplay_id)
        if clip is None:
            raise ValueError(f"Unknown gameplay id '{request.gameplay_id}'")
        if not clip.available or not clip.source:
            raise ValueError(
                f"Gameplay clip '{clip.id}' has no source file. "
                f"Place {clip.id}.mp4 in server/assets/gameplay/ first."
            )
        gameplay = Path(clip.source)

        # --- 2. TTS per line --------------------------------------------------
        store.update(job_id, progress=0.15, message="Synthesizing voiceover")
        from app.providers.tts import registry as tts_registry

        provider = tts_registry.get_tts_provider(
            request.tts_provider.value, voice=request.tts_voice
        )

        line_durations: List[float] = []
        audio_parts: List[Path] = []
        for i, line in enumerate(request.script):
            store.update(
                job_id, progress=0.15,
                message=f"Synthesizing voiceover ({i + 1}/{len(request.script)})",
            )
            audio = await _synthesize_with_retry(provider, line)
            part = workdir / f"line-{i:03d}.{audio.format}"
            part.write_bytes(audio.audio_bytes)
            audio_parts.append(part)
            if compositor.ffprobe_available():
                line_durations.append(
                    await compositor.probe_duration(part) + _LINE_TAIL_SECONDS
                )
            else:  # word-count estimate fallback
                line_durations.append(
                    max(0.8, len(line.split()) * _SECONDS_PER_WORD + _LINE_TAIL_SECONDS)
                )

        store.update(job_id, progress=0.45, message="Stitching voiceover")
        voiceover = await compositor.concat_audio(audio_parts, workdir / "voiceover.mp3")

        # --- 3. Captions + card -------------------------------------------------
        punchlines = {len(request.script) - 1}  # last line is the punchline
        captions = build_caption_timeline(
            request.script, line_durations, punchline_indexes=punchlines
        )

        card = compositor.build_reddit_card(
            title=request.title or request.topic or "r/gaming",
            topic=request.topic or "memeforge",
            out_path=workdir / "card.png",
        )

        # Pre-render kinetic caption PNGs (Pillow) before the ffmpeg pass.
        caption_pngs = compositor.render_caption_pngs(captions, workdir)

        # --- 4. Compose -----------------------------------------------------------
        store.update(job_id, progress=0.6, message="Composing split-screen video")
        sfx = _find_sfx() if request.sfx_on_punchlines else None
        sfx_events = (
            [captions[-1].start] if sfx and captions else None
        )  # boom on the final punchline frame

        output = settings.OUTPUT_DIR / f"{job_id}.mp4"
        cmd = compositor.compose_video(
            card_path=card,
            gameplay_path=gameplay,
            voiceover_path=voiceover,
            captions=captions,
            output_path=output,
            caption_pngs=caption_pngs,
            sfx_path=sfx,
            sfx_events=sfx_events,
        )
        await compositor.run_ffmpeg(cmd)

        # --- 5. Done ---------------------------------------------------------------
        store.update(
            job_id,
            status=JobStatus.completed,
            progress=1.0,
            message="Render complete",
            video_url=f"/outputs/{output.name}",
        )
    except Exception as exc:  # noqa: BLE001 - job runner must never raise
        store.update(
            job_id,
            status=JobStatus.failed,
            message="Render failed",
            error=str(exc),
        )
    finally:
        _cleanup(workdir)


def _cleanup(workdir: Path) -> None:
    """Best-effort temp dir removal."""
    import shutil

    shutil.rmtree(workdir, ignore_errors=True)
