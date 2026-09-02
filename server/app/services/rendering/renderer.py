"""Render orchestrator.

Runs a full pipeline as a background job:

    script lines ──▶ TTS per line ──▶ concat voiceover ──▶ ffmpeg compositor ──▶ mp4
        │                                                        ▲
        ├──▶ kinetic caption timeline (center frame) ──────────┤
        └──▶ floating Reddit post card (Pillow) ──▶ upper-center overlay

The gameplay loop fills the full 1080x1920 vertical frame; the Reddit
post card floats upper-center and fades out once the hook (first line)
has landed. The job store tracks progress; the frontend Preview &
Export node polls `GET /api/v1/render/{job_id}` until status is
completed/failed.
"""

import asyncio
import hashlib
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

from app.core import settings
from app.schemas.render_schema import JobStatus, RenderRequest
from app.services import jobs as jobs_service
from app.services.rendering import compositor
from app.services.rendering.captions import build_caption_timeline
from app.providers.tts.base import WordTiming

# Fallback speech rate when TTS duration probing is unavailable.
_SECONDS_PER_WORD = 0.42

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


def _subreddit_handle(topic: str) -> str:
    """r/ handle for the floating card, derived from the topic."""
    slug = re.sub(r"[^a-z0-9]+", "", (topic or "").lower())[:20]
    return f"r/{slug}" if slug else "r/gaming"


def _viral_metrics(seed: str) -> dict:
    """Deterministic, plausible-looking like/comment/share/award counts."""
    n = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12], 16)
    return {
        "upvotes": 3_000 + n % 480_000,
        "comments": 80 + (n >> 12) % 4_000,
        "shares": 40 + (n >> 24) % 9_000,
        "awards": 2 + (n >> 28) % 3,
    }


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
        # Sync contract: each line's caption window is built from the EXACT
        # probed duration of its audio segment (no synthetic padding), and
        # the segments are concatenated with zero dead space, so captions
        # and voiceover share timestamps end-to-end.
        store.update(job_id, progress=0.15, message="Synthesizing voiceover")
        from app.providers.tts import registry as tts_registry

        provider = tts_registry.get_tts_provider(
            request.tts_provider.value, voice=request.tts_voice
        )

        line_durations: List[float] = []
        line_word_timings: List[Optional[List[WordTiming]]] = []
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
            line_word_timings.append(audio.word_timings)
            if compositor.ffprobe_available():
                line_durations.append(await compositor.probe_duration(part))
            elif audio.word_timings:
                # Best estimate without ffprobe: the last spoken word's end.
                line_durations.append(max(0.8, audio.word_timings[-1].end))
            else:  # word-count estimate fallback
                line_durations.append(max(0.8, len(line.split()) * _SECONDS_PER_WORD))

        store.update(job_id, progress=0.45, message="Stitching voiceover")
        voiceover = await compositor.concat_audio(
            audio_parts, workdir / "voiceover.wav"
        )
        # The concatenated voiceover is the single source of truth for the
        # video length: final cut = exact audio duration + punchline tail.
        total_audio_duration: Optional[float] = None
        if compositor.ffprobe_available():
            total_audio_duration = await compositor.probe_duration(voiceover)
        elif line_durations:
            total_audio_duration = sum(line_durations)

        # --- 3. Captions + card -------------------------------------------------
        punchlines = {len(request.script) - 1}  # last line is the punchline
        captions = build_caption_timeline(
            request.script,
            line_durations,
            punchline_indexes=punchlines,
            total_duration=total_audio_duration,
            word_timings=line_word_timings,
        )

        title = request.title or request.topic or "r/gaming"
        card = compositor.build_reddit_post_card(
            title=title,
            out_path=workdir / "card.png",
            handle=_subreddit_handle(request.topic or title),
            **_viral_metrics(title),
        )

        # Pre-render kinetic caption PNGs (Pillow) before the ffmpeg pass.
        caption_pngs = compositor.render_caption_pngs(captions, workdir)

        # Card stays on screen through the hook (first line), then fades —
        # clamped to the 3-5s window that performs best on shorts feeds.
        card_duration = None
        if line_durations:
            card_duration = min(
                max(line_durations[0] + 0.5, compositor.CARD_MIN_DISPLAY_S),
                compositor.CARD_MAX_DISPLAY_S,
            )

        # --- 4. Compose -----------------------------------------------------------
        store.update(job_id, progress=0.6, message="Composing full-screen video")
        sfx = _find_sfx() if request.sfx_on_punchlines else None
        sfx_events = (
            [captions[-1].start] if sfx and captions else None
        )  # boom on the final punchline frame

        output = settings.OUTPUT_DIR / f"{job_id}.mp4"
        cmd = compositor.compose_video(
            gameplay_path=gameplay,
            voiceover_path=voiceover,
            captions=captions,
            output_path=output,
            card_path=card,
            caption_pngs=caption_pngs,
            sfx_path=sfx,
            sfx_events=sfx_events,
            card_duration=card_duration,
            audio_duration=total_audio_duration,
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
