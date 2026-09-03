"""Stock clip downloader + multi-clip background stitcher.

The studio lets users pick several 3-30s stock clips (Pexels / Pixabay)
as the render background. This module downloads the picked clips and
stitches them, with simple cuts, into ONE continuous vertical video
that covers the exact voiceover duration:

    clip1 ─┐
    clip2 ─┼─▶ normalize (1080x1920, 30fps, cover-crop) ─▶ concat ─▶ background.mp4
    clip3 ─┘        + trim to a per-clip budget

Budgets: clips play in the user's selection order. When their total
outlasts the target duration the overflowing tail clips are dropped and
the crossing clip is trimmed; when the total falls short the sequence
repeats (round-robin) until covered. Cut-based stitching (no crossfade)
keeps one re-encode pass and is robust across arbitrary source codecs —
the transitions land on hard cuts, the classic b-roll style.

The stitched file then feeds the standard compositor pass exactly like
a preset gameplay loop.
"""

import asyncio
from pathlib import Path
from typing import List, Sequence, Tuple

import httpx

from app.core import settings
from app.schemas.render_schema import StockClipRef
from app.services.rendering.compositor import FFMPEG_TIMEOUT_S, run_ffmpeg

# How much shorter/longer than the target the stitched background may be
# before we stop adding/trimming segments (seconds).
_EPSILON_S = 0.05
# Safety cap on concat inputs (ffmpeg graph size + render time).
_MAX_SEGMENTS = 30


def plan_clip_budgets(
    durations: Sequence[float], target_duration: float
) -> List[float]:
    """Per-source trimmed durations so the concat covers `target_duration`.

    Clips are consumed in order; the clip that crosses the target is
    trimmed mid-clip, remaining clips are dropped. When every clip has
    been used and the target still is not covered, the sequence repeats
    from the top (round-robin). Guaranteed to return at least one budget
    when durations is non-empty and target > 0.
    """
    if not durations:
        raise ValueError("no clips to budget")
    if target_duration <= 0:
        raise ValueError("target duration must be positive")

    budgets: List[float] = []
    remaining = target_duration
    idx = 0
    while remaining > _EPSILON_S and len(budgets) < _MAX_SEGMENTS:
        source_duration = max(durations[idx % len(durations)], _EPSILON_S)
        take = min(source_duration, remaining)
        budgets.append(take)
        remaining -= take
        idx += 1
    if remaining > _EPSILON_S and budgets:
        # Segment cap hit: stretch the final budget past its source —
        # ffmpeg's trim clamps to the real length and the compositor's
        # -stream_loop cycles the (slightly short) background to cover.
        budgets[-1] += remaining
    return budgets


async def download_stock_clips(
    refs: Sequence[StockClipRef], workdir: Path
) -> List[Tuple[Path, float]]:
    """Download each picked clip into the render workdir.

    Returns (path, duration_s) pairs — durations come from the search
    metadata (probing would add a round-trip per clip; the budget
    planner tolerates small drift via trim clamping). Raises on the
    first failed download: a missing background clip is fatal for the
    render, and the job store surfaces the error.
    """
    out: List[Tuple[Path, float]] = []
    async with httpx.AsyncClient(
        timeout=settings.STOCK_DOWNLOAD_TIMEOUT_S, follow_redirects=True
    ) as client:
        for i, ref in enumerate(refs):
            dest = workdir / f"stock-{i:02d}.mp4"
            try:
                async with client.stream("GET", ref.url) as resp:
                    resp.raise_for_status()
                    size = 0
                    with open(dest, "wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                            size += len(chunk)
                            if size > settings.STOCK_MAX_CLIP_BYTES:
                                raise RuntimeError(
                                    f"clip '{ref.label or ref.id}' exceeds the "
                                    f"{settings.STOCK_MAX_CLIP_BYTES // (1 << 20)}MB cap"
                                )
                            fh.write(chunk)
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"stock clip download failed ({ref.provider}:{ref.id}): {exc}"
                ) from exc
            if size == 0:
                raise RuntimeError(
                    f"stock clip download returned no bytes ({ref.provider}:{ref.id})"
                )
            out.append((dest, ref.duration_s))
    return out


def stitch_background_args(
    clips: Sequence[Tuple[Path, float]],
    output: Path,
    target_duration: float,
) -> List[str]:
    """Build the ffmpeg argv that stitches clips into one background.

    Each clip is normalized to the render canvas (scale to cover
    1080x1920, center-crop, 30fps) and trimmed to its budget; the
    segments concatenate with the `concat` filter (hard cuts). Audio is
    dropped — the voiceover is the only audio track in the final render.
    """
    if not clips:
        raise ValueError("no stock clips to stitch")

    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS
    budgets = plan_clip_budgets([d for _, d in clips], target_duration)

    inputs: List[str] = [settings.FFMPEG_BIN, "-y"]
    filters: List[str] = []
    labels: List[str] = []
    for i, ((path, _duration), budget) in enumerate(zip(clips, budgets)):
        inputs += ["-i", str(path)]
        filters.append(
            f"[{i}:v]trim=duration={budget:.3f},setpts=PTS-STARTPTS,"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={fps},setsar=1,format=yuv420p[s{i}]"
        )
        labels.append(f"[s{i}]")

    if len(labels) == 1:
        filter_complex = filters[0].replace("[s0]", "[v]", 1)
    else:
        filter_complex = ";".join(filters) + ";" + "".join(labels) + (
            f"concat=n={len(labels)}:v=1:a=0[v]"
        )

    return inputs + [
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output),
    ]


async def stitch_background(
    clips: Sequence[Tuple[Path, float]],
    output: Path,
    target_duration: float,
) -> Path:
    """Run the stitch ffmpeg command (async, with the shared timeout)."""
    await asyncio.wait_for(
        run_ffmpeg(stitch_background_args(clips, output, target_duration)),
        timeout=FFMPEG_TIMEOUT_S,
    )
    return output
