"""FFmpeg full-screen vertical compositor.

Builds and runs the ffmpeg command that turns (background loop, optional
headline card, voiceover, caption timeline) into a vertical 1080x1920
short in the classic viral layout:

    ┌───────────────────────────────┐
    │   ╭─────────────────────╮     │  floating headline card
    │   │  BOLD HOOK HEADLINE  │     │  ("hook" style) or quote card
    │   │  OR QUOTED LINE      │     │  ("quote" style), pinned
    │   │                      │     │  ~15% from the top, fades out
    │   ╰─────────────────────╯     │  after the hook line lands
    │                               │
    │        KINETIC                │  1-2 words per frame, dead
    │        CAPTIONS               │  center of the frame, massive
    │        1-2 WORDS              │  bold font + heavy black stroke
    │                               │
    │      background loop          │  FULL-SCREEN background: the
    │      (fills the whole         │  loop is scaled to cover the
    │      1080×1920 frame,         │  entire 9:16 frame edge-to-edge
    │      edge to edge)            │  behind the card + captions
    └───────────────────────────────┘

The background loop fills the full vertical frame via
`scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`
(no 50/50 split, no static top section). Long background assets (5-120
minute clips) get a random `-ss` seek in-point so every render uses
completely fresh footage. The card and each caption frame are
pre-rendered as transparent PNGs with Pillow and composited with the
`overlay` filter — deliberately avoiding `drawtext`, which needs an
ffmpeg built with libfreetype (Homebrew's is not). `moviepy` is an
acceptable alternative wrapper for complex effects; ffmpeg filter
graphs are used here because they are fast, dependency-light, and
deterministic.

All ffmpeg/ffprobe calls run through asyncio subprocess (with timeouts)
so renders never block or hang the event loop.
"""

import asyncio
import random
import shutil
from pathlib import Path
from typing import List, Optional, Sequence

from app.core import settings
from app.services.rendering.captions import CaptionFrame

# --- Caption look: massive bold text with a heavy black stroke ------------
CAPTION_FONT_SIZE = 108
CAPTION_STROKE_WIDTH = 10  # the "heavy stroke" kinetic-caption aesthetic
CAPTION_COLOR = "white"
CAPTION_STROKE_COLOR = "black"
PUNCHLINE_COLOR = "FDE047"  # yellow pop on punchlines
PUNCHLINE_FONT_SIZE = 126

# --- Floating headline / quote card ----------------------------------------
CARD_WIDTH = 920  # of 1080 — floats with margins
CARD_CORNER_RADIUS = 44
CARD_TOP_FRACTION = 0.15  # overlay y = main_h * 0.15 (upper center)
CARD_FADE_IN_S = 0.25
CARD_FADE_OUT_S = 0.6
CARD_MIN_DISPLAY_S = 3.0  # hook visibility window clamp
CARD_MAX_DISPLAY_S = 5.0
CARD_STYLES = ("hook", "quote")  # "none" never reaches the card builder

# --- Random in-point for long background assets -----------------------------
# When a background clip is far longer than the requested video, pick a
# random start timestamp so repeated renders of the same asset surface
# completely different footage instead of always playing from the top.
SEEK_MARGIN_S = 5.0  # only seek when the clip outlasts the cut by > 5s
SEEK_TAIL_PAD_S = 1.0  # keep at least 1s of headroom after the cut ends

# Safety timeouts so a stalled network read or subprocess can't hang a job.
FFMPEG_TIMEOUT_S = 600.0
FFPROBE_TIMEOUT_S = 30.0

# Tight tail after the voiceover ends: the last caption frame lingers on
# screen for punchline resonance while the audio stream has already
# finished. The final video length is exactly audio duration + this tail.
VIDEO_TAIL_S = 0.3

# Massive display fonts, tried in order: Impact/Anton/Montserrat Black are
# the meme standard; Arial Bold / DejaVu Bold are the portable fallbacks.
_FONT_CANDIDATES = [
    settings.FONTS_DIR / "Anton-Regular.ttf",
    settings.FONTS_DIR / "Montserrat-Black.ttf",
    settings.FONTS_DIR / "Inter-Bold.ttf",
    Path("/System/Library/Fonts/Supplemental/Impact.ttf"),  # macOS
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),  # macOS
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),  # Debian
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),  # Arch
]




def ffmpeg_available() -> bool:
    return shutil.which(settings.FFMPEG_BIN) is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


async def probe_video_duration(video_path: Path) -> float:
    """Exact duration of a video file in seconds, via ffprobe.

    Mirrors `probe_duration` but selects the video stream: the v:0
    stream duration wins (frame-exact for most mp4s), the container
    format duration is the fallback. Used to decide whether a long
    background asset deserves a random seek in-point.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=duration:format=duration",
        "-of", "json",
        str(video_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await asyncio.wait_for(
        proc.communicate(), timeout=FFPROBE_TIMEOUT_S
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}")
    duration = duration_from_probe(stdout.decode(errors="replace"))
    if duration is None:
        raise RuntimeError(f"ffprobe found no duration for {video_path}")
    return duration


def compute_background_seek(
    clip_duration: float,
    requested_duration: float,
    rng: Optional[random.Random] = None,
) -> Optional[float]:
    """Random in-point (seconds) for a background clip, or None.

    Long background assets (e.g. 5-120 minute b-roll clips) are only used
    for the first `requested_duration` seconds of a render. When the clip
    outlasts the requested cut by more than `SEEK_MARGIN_S`, a random
    start timestamp is picked so different renders of the same asset get
    completely fresh footage. Tight clips (short loops meant to repeat)
    return None: play them from the top and let `-stream_loop` cycle.
    """
    if clip_duration <= 0 or requested_duration <= 0:
        return None
    if clip_duration <= requested_duration + SEEK_MARGIN_S:
        return None
    max_start = clip_duration - requested_duration - SEEK_TAIL_PAD_S
    if max_start <= 0:
        return None
    picker = rng if rng is not None else random
    return picker.uniform(0.0, max_start)


async def probe_duration(media_path: Path) -> float:
    """Exact duration of an audio/video file in seconds, via ffprobe.

    Prefers the audio stream's own duration — for mp3 it is derived from
    the real decoded frame count (frame-exact, matching what ffmpeg
    decodes when concatenating), and for PCM/WAV it is sample-exact. The
    container's format duration is the fallback (video files, damaged
    streams). The returned value is what the voiceover concatenation and
    the caption timeline are both built on, so audio and captions share
    timestamps end-to-end.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=duration:format=duration",
        "-of", "json",
        str(media_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await asyncio.wait_for(
        proc.communicate(), timeout=FFPROBE_TIMEOUT_S
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {media_path}")
    duration = duration_from_probe(stdout.decode(errors="replace"))
    if duration is None:
        raise RuntimeError(f"ffprobe found no duration for {media_path}")
    return duration


def duration_from_probe(probe_output: str) -> Optional[float]:
    """Pick the most exact duration from an ffprobe JSON payload.

    The audio stream's duration wins (decoded-frame / sample accurate);
    the container format duration is the fallback. Returns None when
    neither is usable, so callers can raise a precise error.
    """
    import json

    try:
        payload = json.loads(probe_output)
    except ValueError:
        return None
    streams = payload.get("streams") or [{}]
    stream = streams[0] or {}
    try:
        if stream.get("duration") is not None:
            return float(stream["duration"])
    except (TypeError, ValueError):
        pass
    try:
        fmt_duration = payload.get("format", {}).get("duration")
        if fmt_duration is not None:
            return float(fmt_duration)
    except (TypeError, ValueError):
        pass
    return None


def _load_font(size: int):
    """Bold truetype font (Impact-style first); falls back to Pillow default."""
    from PIL import ImageFont

    for cand in _FONT_CANDIDATES:
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size)
            except OSError:
                continue
    return ImageFont.load_default()


# --- Headline / quote card (Pillow) ------------------------------------------

def _wrap_text(draw, text: str, font, max_width: int) -> List[str]:
    """Greedy word-wrap to `max_width` pixels."""
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# Brand accent used on the hook card's edge strip.
_CARD_ACCENT = (139, 92, 246, 255)  # violet


def build_headline_card(
    title: str,
    out_path: Path,
    style: str = "hook",
    width: int = CARD_WIDTH,
) -> Path:
    """Render the floating top card as a transparent PNG.

    A clean, generic rounded card overlaid on the upper-center of the
    full-screen background. Two styles:

    - ``hook``  — bold headline with a violet accent strip on the left
                  edge, for the opening hook / headline.
    - ``quote`` — oversized quote mark above a quoted line, for
                  quote-style videos.

    Everything is drawn at 2x and downscaled for smooth (anti-aliased)
    edges. Callers pass ``card_style="none"`` by not building a card at
    all (a clean full video without card).
    """
    if style not in CARD_STYLES:
        raise ValueError(f"unknown card style '{style}' (expected {CARD_STYLES})")

    from PIL import Image, ImageDraw

    scale = 2  # supersample for anti-aliased corners and icons
    pad = 48
    is_quote = style == "quote"
    title_size = 40 if is_quote else 46
    title_line_h = 54 if is_quote else 60
    quote_mark_size = 96
    gap_quote_title = 8
    accent_w = 8  # hook card: accent strip inside the left edge

    # All geometry/fonts are computed directly at the supersampled scale.
    def S(v: float) -> float:
        return v * scale

    title_font = _load_font(S(title_size))
    quote_font = _load_font(S(quote_mark_size))

    # Measure text with a scratch canvas.
    probe = Image.new("RGBA", (8, 8))
    probe_draw = ImageDraw.Draw(probe)
    text_pad = pad + (accent_w + 18 if not is_quote else 0)
    inner_w = width - text_pad - pad
    title_lines = _wrap_text(probe_draw, title, title_font, S(inner_w))[:4]
    if not title_lines:
        title_lines = [""]

    height = pad * 2 + len(title_lines) * title_line_h
    if is_quote:
        height += quote_mark_size + gap_quote_title

    # Canvas with room for a soft drop shadow below the card body.
    canvas = Image.new("RGBA", (S(width), S(height + 14)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Drop shadow, then the near-opaque white card body.
    draw.rounded_rectangle(
        [S(0), S(12), S(width - 1), S(height + 13)],
        radius=S(CARD_CORNER_RADIUS), fill=(0, 0, 0, 70),
    )
    draw.rounded_rectangle(
        [S(0), S(0), S(width - 1), S(height - 1)],
        radius=S(CARD_CORNER_RADIUS), fill=(255, 255, 255, 243),
    )

    dark = (15, 17, 21, 255)
    muted = (113, 118, 123, 255)

    if is_quote:
        # Oversized decorative quote mark above the quoted text.
        draw.text((S(pad), S(pad - 10)), "\u201C", font=quote_font, fill=muted)
        y = S(pad + quote_mark_size + gap_quote_title)
        for line in title_lines:
            draw.text((S(pad), y), line, font=title_font, fill=dark)
            y += S(title_line_h)
    else:
        # Bold hook headline with a violet accent strip on the left edge.
        draw.rounded_rectangle(
            [S(pad), S(pad), S(pad + accent_w), S(height - pad)],
            radius=S(accent_w / 2), fill=_CARD_ACCENT,
        )
        y = S(pad)
        for line in title_lines:
            draw.text((S(text_pad), y), line, font=title_font, fill=dark)
            y += S(title_line_h)

    card = canvas.resize((width, height + 14), Image.LANCZOS)
    card.save(out_path, format="PNG")
    return out_path


def render_caption_pngs(
    frames: Sequence[CaptionFrame], workdir: Path
) -> List[Path]:
    """Pre-render each caption frame as a transparent PNG (Pillow).

    Heavy stroke text centered on a full-width canvas; punchlines get the
    yellow pop. The compositor centers these PNGs in the middle of the
    vertical frame. PNGs are burned in with `overlay` filters, keeping
    the pipeline free of ffmpeg's optional drawtext filter.
    """
    from PIL import Image, ImageDraw

    pngs: List[Path] = []
    for i, frame in enumerate(frames):
        font = _load_font(
            PUNCHLINE_FONT_SIZE if frame.is_punchline else CAPTION_FONT_SIZE
        )
        color = f"#{PUNCHLINE_COLOR}" if frame.is_punchline else CAPTION_COLOR

        # Measure with a scratch canvas, then draw the real one.
        probe = Image.new("RGBA", (8, 8))
        draw = ImageDraw.Draw(probe)
        bbox = draw.textbbox((0, 0), frame.words, font=font,
                             stroke_width=CAPTION_STROKE_WIDTH)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

        canvas = Image.new("RGBA", (settings.VIDEO_WIDTH, text_h + 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text(
            ((settings.VIDEO_WIDTH - text_w) / 2 - bbox[0], 20 - bbox[1]),
            frame.words,
            font=font,
            fill=color,
            stroke_width=CAPTION_STROKE_WIDTH,
            stroke_fill=CAPTION_STROKE_COLOR,
        )

        out = workdir / f"cap-{i:03d}.png"
        canvas.save(out, format="PNG")
        pngs.append(out)
    return pngs


def _caption_overlay_chain(
    caption_pngs: Sequence[Path],
    frames: Sequence[CaptionFrame],
    first_input_index: int,
    base_label: str,
) -> tuple[List[str], List[str]]:
    """Overlay filter snippets chaining the caption PNGs onto the video.

    Returns (filter_snippets, input_args). Each PNG enters as its own input
    and is overlaid dead-center of the vertical frame (both axes), visible
    only during its time window (`enable=between(t,...)`).
    """
    inputs: List[str] = []
    filters: List[str] = []
    prev = base_label
    for i, (png, frame) in enumerate(zip(caption_pngs, frames)):
        idx = first_input_index + i
        inputs += ["-i", str(png)]
        out = f"[cap{i}]" if i < len(caption_pngs) - 1 else "[v]"
        filters.append(
            f"{prev}[{idx}:v]overlay=x=(main_w-overlay_w)/2:"
            f"y=(main_h-overlay_h)/2:"
            f"enable='between(t,{frame.start:.3f},{frame.end:.3f})'{out}"
        )
        prev = out
    return filters, inputs


def final_cut_duration(
    captions: Sequence[CaptionFrame], audio_duration: Optional[float]
) -> float:
    """Exact output length of a render.

    When `audio_duration` (the probed voiceover length) is given, the
    output runs exactly that plus VIDEO_TAIL_S so the audio and caption
    tracks share start/end timestamps and the punchline gets a tight
    resonance tail. Without a probed audio length, the caption end
    drives the cut.
    """
    if audio_duration is not None:
        return audio_duration + VIDEO_TAIL_S
    return max(1.0, captions[-1].end if captions else 3.0) + VIDEO_TAIL_S


def compose_video(
    gameplay_path: Path,
    voiceover_path: Path,
    captions: Sequence[CaptionFrame],
    output_path: Path,
    card_path: Optional[Path] = None,
    caption_pngs: Optional[Sequence[Path]] = None,
    workdir: Optional[Path] = None,
    sfx_path: Optional[Path] = None,
    sfx_events: Optional[List[float]] = None,
    card_duration: Optional[float] = None,
    audio_duration: Optional[float] = None,
    background_seek: Optional[float] = None,
) -> List[str]:
    """Assemble the full ffmpeg argv for the full-screen vertical render.

    Layout: the background fills the whole 1080x1920 frame; the headline
    card floats upper-center and fades out after `card_duration` seconds
    (None keeps it pinned for the whole video); kinetic captions burn in
    dead center. Caption PNGs are rendered on the fly when not supplied.

    Duration: when `audio_duration` (the probed voiceover length) is
    given, the output runs exactly that plus VIDEO_TAIL_S so the audio
    and caption tracks share start/end timestamps and the punchline gets
    a tight resonance tail.

    Background seek: `background_seek` (seconds) is passed to ffmpeg as
    an input `-ss` before `-stream_loop -1 -i`, so long background
    assets start at a random in-point and every render surfaces fresh
    footage. None plays the clip from the top.
    """
    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS

    if caption_pngs is None and captions:
        if workdir is None:
            workdir = output_path.parent
        caption_pngs = render_caption_pngs(captions, workdir)
    caption_pngs = caption_pngs or []

    has_card = card_path is not None
    has_captions = bool(captions) and bool(caption_pngs)

    inputs: List[str] = [settings.FFMPEG_BIN, "-y"]
    if background_seek is not None:
        # Input seek: the demuxer jumps straight to the in-point (fast)
        # and -stream_loop then cycles whatever remains of the clip.
        inputs += ["-ss", f"{background_seek:.3f}"]
    inputs += [
        "-stream_loop", "-1", "-i", str(gameplay_path),  # 0: fullscreen bg
    ]
    next_index = 1
    card_index: Optional[int] = None
    if has_card:
        inputs += ["-loop", "1", "-i", str(card_path)]  # floating card
        card_index = next_index
        next_index += 1

    voiceover_index = next_index
    inputs += ["-i", str(voiceover_path)]
    next_index += 1

    sfx_index: Optional[int] = None
    if sfx_path and sfx_events:
        inputs += ["-i", str(sfx_path)]
        sfx_index = next_index
        next_index += 1

    first_caption_index = next_index

    # --- Video graph ---------------------------------------------------------
    # Full-screen gameplay background: scale to cover, then center-crop to
    # the exact 1080x1920 frame — edge to edge, no letterboxing.
    parts: List[str] = [
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps},setsar=1[bg]"
    ]

    if has_card:
        # Card: fade in at the start, fade out once the hook has landed.
        card_chain = (
            f"[{card_index}:v]format=rgba,"
            f"fade=t=in:st=0:d={CARD_FADE_IN_S}:alpha=1"
        )
        if card_duration is not None:
            fade_start = max(0.0, card_duration - CARD_FADE_OUT_S)
            card_chain += (
                f",fade=t=out:st={fade_start:.3f}:d={CARD_FADE_OUT_S}:alpha=1"
            )
        parts.append(card_chain + "[card]")
        card_out = "[cardbg]" if has_captions else "[v]"
        parts.append(
            f"[bg][card]overlay=x=(main_w-overlay_w)/2:"
            f"y=main_h*{CARD_TOP_FRACTION}{card_out}"
        )

    if has_captions:
        base_label = "[cardbg]" if has_card else "[bg]"
        caption_filters, caption_inputs = _caption_overlay_chain(
            caption_pngs, captions, first_caption_index, base_label
        )
        inputs += caption_inputs
        parts.extend(caption_filters)
    elif not has_card:
        # Nothing overlays the background: [bg] is the final video stream.
        parts[0] = parts[0].replace("[bg]", "[v]")

    # Duration: exact audio stream length + the tight punchline tail. The
    # caption overlay windows are built on the same audio timeline, so
    # video, audio and captions start and end together.
    duration = final_cut_duration(captions, audio_duration)

    # --- Audio graph: voiceover (+ delayed sfx mixed in when provided) ------
    # The mixed track is padded to the full cut (`apad=whole_dur`) so the
    # punchline SFX rings through the tail instead of being truncated at
    # the voiceover's end.
    if sfx_index is not None and sfx_events:
        delays = "|".join(f"{int(t * 1000)}:all=1" for t in sfx_events)
        parts.append(
            f"[{voiceover_index}:a]aresample=44100[vo];"
            f"[{sfx_index}:a]aresample=44100,adelay='{delays}'[sfx];"
            f"[vo][sfx]amix=inputs=2:duration=longest:dropout_transition=0,"
            f"volume=1.5,apad=whole_dur={duration:.3f}[a]"
        )
    else:
        parts.append(
            f"[{voiceover_index}:a]aresample=44100,"
            f"apad=whole_dur={duration:.3f}[a]"
        )

    filter_complex = ";".join(parts)

    return inputs + [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{duration:.3f}",
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(output_path),
    ]


async def run_ffmpeg(args: Sequence[str]) -> None:
    """Run an ffmpeg command as an async subprocess (with a timeout)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=FFMPEG_TIMEOUT_S
    )
    if proc.returncode != 0:
        tail = stderr.decode(errors="replace")[-2000:]
        raise RuntimeError(f"ffmpeg exited {proc.returncode}:\n{tail}")


def concat_audio_args(
    parts: List[Path], output: Path, gap_ms: int = 0
) -> List[str]:
    """Build the ffmpeg argv that concatenates per-line TTS audio.

    Every part is decoded, resampled to a common 44.1kHz mono format and
    stitched with the `concat` *filter* (not the demuxer), so line
    boundaries land at exactly the sum of the probed per-part decoded
    durations — no mp3 frame rounding, no dead space. The output is WAV:
    sample-exact, so its probed duration equals the true audio length.

    `gap_ms > 0` injects exactly that much silence after every line but
    the last (pacing pauses); the caller must then include the gap in
    the caption timeline. The render pipeline uses 0: no dead space.
    """
    if not parts:
        raise ValueError("no audio parts to concat")

    inputs: List[str] = [settings.FFMPEG_BIN, "-y"]
    filters: List[str] = []
    concat_labels: List[str] = []
    idx = 0
    for i, part in enumerate(parts):
        inputs += ["-i", str(part)]
        filters.append(
            f"[{idx}:a]aresample=44100,"
            f"aformat=sample_fmts=s16:channel_layouts=mono[a{idx}]"
        )
        concat_labels.append(f"[a{idx}]")
        idx += 1
        if gap_ms > 0 and i < len(parts) - 1:
            inputs += [
                "-f", "lavfi", "-t", f"{gap_ms / 1000:.3f}",
                "-i", "anullsrc=r=44100:cl=mono",
            ]
            filters.append(
                f"[{idx}:a]aformat=sample_fmts=s16:channel_layouts=mono[a{idx}]"
            )
            concat_labels.append(f"[a{idx}]")
            idx += 1

    if len(concat_labels) == 1:
        # Single part: normalize it directly, no concat filter needed.
        filter_complex = filters[0].replace("[a0]", "[a]", 1)
    else:
        filter_complex = ";".join(filters) + ";" + "".join(concat_labels) + (
            f"concat=n={len(concat_labels)}:v=0:a=1[a]"
        )

    return inputs + [
        "-filter_complex", filter_complex,
        "-map", "[a]",
        "-c:a", "pcm_s16le",
        str(output),
    ]


async def concat_audio(
    parts: List[Path], output: Path, gap_ms: int = 0
) -> Path:
    """Concatenate per-line TTS audio into one sample-exact voiceover.

    See `concat_audio_args` for the exactness contract. Default gap is
    0 (no dead space between lines).
    """
    await run_ffmpeg(concat_audio_args(parts, output, gap_ms=gap_ms))
    return output
