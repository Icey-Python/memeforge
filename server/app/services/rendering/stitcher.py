"""Stock clip downloader + multi-clip background stitcher.

The studio lets users pick several 3-30s stock clips (Pexels / Pixabay)
as the render background. This module downloads the picked clips and
stitches them, with simple cuts, into ONE continuous vertical video
that covers the exact voiceover duration:

    clip1 ─┐
    clip2 ─┼─▶ normalize (1080x1920, 30fps, cover-crop) ─▶ concat ─▶ background.mp4
    clip3 ─┘        + trim to a per-clip budget

Two planning modes:
- Ordered playlist (`plan_clip_budgets`): clips play in the user's
  selection order, each for its full length (or a trimmed tail).
- Fast-switching montage (`plan_montage_segments`): every clip plays a
  short 1.5-3s segment before the cut — the auto-selected keyword
  montage rhythm for vertical shorts — cycling clips with fresh
  in-points when the sequence repeats.

Budgets: when the total outlasts the target duration the overflowing
tail clips are dropped and the crossing clip is trimmed; when the
total falls short the sequence repeats (round-robin) until covered.
Cut-based stitching (no crossfade) keeps one re-encode pass and is
robust across arbitrary source codecs — the transitions land on hard
cuts, the classic b-roll style.

The stitched file then feeds the standard compositor pass exactly like
a preset gameplay loop.
"""

import asyncio
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

import httpx

from app.core import settings
from app.schemas.render_schema import StockClipRef
from app.services.rendering.compositor import FFMPEG_TIMEOUT_S, run_ffmpeg

# How much shorter/longer than the target the stitched background may be
# before we stop adding/trimming segments (seconds).
_EPSILON_S = 0.05
# Safety cap on concat inputs (ffmpeg graph size + render time).
_MAX_SEGMENTS = 30

# --- Fast-switching montage ------------------------------------------------
#
# Auto-selected keyword montages cut each clip to a short segment so the
# background keeps pace with the script: a hard cut every ~1.5-3s, the
# classic b-roll montage rhythm for vertical shorts. Segment lengths
# cycle max → mid → min so cuts don't land on a metronome (all-3.0s
# cuts read as mechanical).
MONTAGE_SEGMENT_MIN_S = 1.5
MONTAGE_SEGMENT_MAX_S = 3.0
# Safety cap on montage segments (ffmpeg graph size). Beyond the cap the
# compositor's -stream_loop cycles the stitched background to cover.
_MAX_MONTAGE_SEGMENTS = 120


class StitchSegment(NamedTuple):
    """One cut of the stitched background.

    `clip_index` points into the source clip list; `start_s` is the
    in-point within that clip (montage cycles continue a clip from
    where its previous segment stopped); `duration_s` is the cut length.
    """

    clip_index: int
    start_s: float
    duration_s: float


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


def _montage_rhythm(n: int, min_s: float, max_s: float) -> float:
    """Segment length #n of the max → mid → min cut rhythm."""
    mid = (min_s + max_s) / 2
    return (max_s, mid, min_s)[n % 3]


def plan_montage_segments(
    durations: Sequence[float],
    target_duration: float,
    min_segment_s: float = MONTAGE_SEGMENT_MIN_S,
    max_segment_s: float = MONTAGE_SEGMENT_MAX_S,
) -> List[StitchSegment]:
    """Fast-switching plan: every clip plays a short segment, then cuts.

    Each source clip contributes a `min_segment_s`-`max_segment_s` cut
    (rhythm-cycled so cuts don't land on a metronome); when a clip is
    shorter than its segment the real length wins. Clips are consumed
    in order; once every clip has played, later passes CONTINUE each
    clip from where its previous segment stopped (wrapping to the top
    when exhausted), so cycles surface fresh footage instead of
    replaying the same 3 seconds. The plan covers `target_duration`
    exactly (up to the segment cap; the compositor's -stream_loop then
    cycles the stitched background).

    Guaranteed to return at least one segment when durations is
    non-empty (with some clip > _EPSILON_S) and target > 0.
    """
    if not durations:
        raise ValueError("no clips to budget")
    if target_duration <= 0:
        raise ValueError("target duration must be positive")

    segments: List[StitchSegment] = []
    remaining = target_duration
    # Cumulative in-point per clip (wraps within the clip when exhausted).
    taken = [0.0] * len(durations)
    while remaining > _EPSILON_S and len(segments) < _MAX_MONTAGE_SEGMENTS:
        progressed = False
        for i, clip_duration in enumerate(durations):
            if remaining <= _EPSILON_S:
                break
            if clip_duration <= _EPSILON_S:
                continue
            start = taken[i] % clip_duration
            available = clip_duration - start
            if available < min_segment_s and clip_duration >= min_segment_s:
                # A normal clip's leftover is shorter than a proper cut:
                # continue from the top — later cuts surface fresh footage
                # instead of a sub-second blip. (Clips shorter than
                # min_segment_s always play whole.)
                start = 0.0
                available = clip_duration
            if remaining <= max_segment_s + _EPSILON_S:
                # Final stretch: take what's left (≤ max_segment_s) so the
                # plan covers the target exactly, with no sliver segment.
                take = available if available <= remaining else remaining
            else:
                take = min(
                    _montage_rhythm(len(segments), min_segment_s, max_segment_s),
                    available,
                )
            if take <= _EPSILON_S:
                continue
            segments.append(StitchSegment(i, start, take))
            taken[i] = start + take
            remaining -= take
            progressed = True
        if not progressed:
            break  # pathological input (all clips slivers) — stop safely
    return segments


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
    segments: Optional[Sequence[StitchSegment]] = None,
) -> List[str]:
    """Build the ffmpeg argv that stitches clips into one background.

    Each segment is normalized to the render canvas (scale to cover
    1080x1920, center-crop, 30fps) and trimmed to its in-point + length;
    the segments concatenate with the `concat` filter (hard cuts —
    seamless montage transitions). `segments=None` plans whole-clip
    budgets via `plan_clip_budgets` (the ordered-playlist mode);
    `plan_montage_segments` output drives the fast-switching mode.
    Repeated clip indexes are fine — the file is opened once per
    segment so each cut gets its own in-point. Audio is dropped — the
    voiceover is the only audio track in the final render.
    """
    if not clips:
        raise ValueError("no stock clips to stitch")

    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS
    if segments is None:
        budgets = plan_clip_budgets([d for _, d in clips], target_duration)
        segments = [
            StitchSegment(i, 0.0, budget) for i, budget in enumerate(budgets)
        ]
    if not segments:
        raise ValueError("no segments to stitch")

    inputs: List[str] = [settings.FFMPEG_BIN, "-y"]
    filters: List[str] = []
    labels: List[str] = []
    for j, seg in enumerate(segments):
        inputs += ["-i", str(clips[seg.clip_index][0])]
        filters.append(
            f"[{j}:v]trim=start={seg.start_s:.3f}:duration={seg.duration_s:.3f},"
            f"setpts=PTS-STARTPTS,"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={fps},setsar=1,format=yuv420p[s{j}]"
        )
        labels.append(f"[s{j}]")

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
    segments: Optional[Sequence[StitchSegment]] = None,
) -> Path:
    """Run the stitch ffmpeg command (async, with the shared timeout)."""
    await asyncio.wait_for(
        run_ffmpeg(
            stitch_background_args(clips, output, target_duration, segments)
        ),
        timeout=FFMPEG_TIMEOUT_S,
    )
    return output
