"""FFmpeg full-screen vertical compositor.

Builds and runs the ffmpeg command that turns (gameplay loop, floating
Reddit post card, voiceover, caption timeline) into a vertical
1080x1920 short in the authentic viral Reddit/TikTok layout:

    ┌───────────────────────────────┐
    │   ╭─────────────────────╮     │  floating Reddit post card
    │   │ ⬤ r/gaming ✔ 🏆 ✨ │     │  (avatar + handle + verified +
    │   │  BOLD POST TITLE     │     │   awards + metrics), pinned
    │   │  ♥ 24.5K  💬 891  ↗ │     │   ~15% from the top, fades out
    │   ╰─────────────────────╯     │  after the hook line lands
    │                               │
    │        KINETIC                │  1-2 words per frame, dead
    │        CAPTIONS               │  center of the frame, massive
    │        1-2 WORDS              │  bold font + heavy black stroke
    │                               │
    │      gameplay loop            │  FULL-SCREEN background: the
    │      (fills the whole         │  loop is scaled to cover the
    │      1080×1920 frame,         │  entire 9:16 frame edge-to-edge
    │      edge to edge)            │  behind the card + captions
    └───────────────────────────────┘

The gameplay loop fills the full vertical frame via
`scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`
(no 50/50 split, no static top section). The Reddit card and each
caption frame are pre-rendered as transparent PNGs with Pillow and
composited with the `overlay` filter — deliberately avoiding `drawtext`,
which needs an ffmpeg built with libfreetype (Homebrew's is not).
`moviepy` is an acceptable alternative wrapper for complex effects;
ffmpeg filter graphs are used here because they are fast,
dependency-light, and deterministic.

All ffmpeg/ffprobe calls run through asyncio subprocess (with timeouts)
so renders never block or hang the event loop.
"""

import asyncio
import math
import shutil
from pathlib import Path
from typing import List, Optional, Sequence

from app.core import settings
from app.services.rendering.captions import CaptionFrame

# --- Caption look: massive bold text with a heavy black stroke ------------
CAPTION_FONT_SIZE = 108
CAPTION_STROKE_WIDTH = 10  # the "heavy stroke" meme aesthetic
CAPTION_COLOR = "white"
CAPTION_STROKE_COLOR = "black"
PUNCHLINE_COLOR = "FDE047"  # yellow pop on punchlines
PUNCHLINE_FONT_SIZE = 126

# --- Floating Reddit post card ---------------------------------------------
CARD_WIDTH = 920  # of 1080 — floats with margins like the real apps
CARD_CORNER_RADIUS = 44
CARD_TOP_FRACTION = 0.15  # overlay y = main_h * 0.15 (upper center)
CARD_FADE_IN_S = 0.25
CARD_FADE_OUT_S = 0.6
CARD_MIN_DISPLAY_S = 3.0  # hook visibility window clamp
CARD_MAX_DISPLAY_S = 5.0

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

# Color emoji fonts for the award row (best effort; vector medals fallback).
_EMOJI_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),  # macOS
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),  # Debian
    Path("/usr/share/fonts/noto-color-emoji/NotoColorEmoji.ttf"),
]


def ffmpeg_available() -> bool:
    return shutil.which(settings.FFMPEG_BIN) is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


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


def _load_emoji_font(preferred_size: int):
    """Best-effort color-emoji font; bitmap emoji fonts only allow certain
    pixel sizes, so several candidates are tried. Returns (font, size)."""
    from PIL import ImageFont

    sizes = [preferred_size, 40, 36, 32, 109]
    for cand in _EMOJI_FONT_CANDIDATES:
        if not cand.exists():
            continue
        for size in sizes:
            try:
                return ImageFont.truetype(str(cand), size), size
            except OSError:
                continue
    return None, 0


# --- Reddit post card (Pillow) ---------------------------------------------

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


def _format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _handle_initial(handle: str) -> str:
    """Avatar glyph: first letter of the subreddit/handle ('r/gaming' → G)."""
    for part in handle.replace("@", "/").split("/"):
        for ch in part:
            if ch.isalpha():
                return ch.upper()
    return "R"


def _draw_verified_badge(draw, cx: float, cy: float, r: float) -> None:
    """Blue verified check circle, Twitter/Reddit style."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(29, 155, 240, 255))
    width = max(3, int(r * 0.24))
    draw.line(
        [(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.08, cy + r * 0.34)],
        fill=(255, 255, 255, 255), width=width,
    )
    draw.line(
        [(cx - r * 0.08, cy + r * 0.34), (cx + r * 0.46, cy - r * 0.3)],
        fill=(255, 255, 255, 255), width=width,
    )


def _draw_medal(draw, cx: float, cy: float, r: float, fill, ring) -> None:
    """Vector fallback for award emojis: a small medal disc + star."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ring)
    inner = r * 0.78
    draw.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=fill)
    star_r = r * 0.45
    points = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = star_r if i % 2 == 0 else star_r * 0.45
        points.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(points, fill=(255, 255, 255, 230))


def _draw_awards(draw, x: float, cy: float, count: int, size: int = 34) -> None:
    """Row of award emojis (🏆 🥇 ✨ 🏅); falls back to vector medals when
    no color-emoji font is available."""
    emojis = ["\N{TROPHY}", "\N{FIRST PLACE MEDAL}", "\N{SPARKLES}", "\N{SPORTS MEDAL}"]
    font, font_size = _load_emoji_font(size)
    if font is not None:
        try:
            for i, emoji in enumerate(emojis[:count]):
                draw.text(
                    (x + i * (font_size + 6), cy - font_size),
                    emoji, font=font, embedded_color=True,
                )
            return
        except Exception:  # noqa: BLE001 - emoji font quirks → medal fallback
            pass
    colors = [
        ((255, 214, 10, 255), (180, 130, 10, 255)),  # gold
        ((200, 208, 214, 255), (140, 148, 156, 255)),  # silver
        ((205, 127, 50, 255), (150, 90, 35, 255)),  # bronze
    ]
    r = size / 2
    for i in range(count):
        fill, ring = colors[i % len(colors)]
        _draw_medal(draw, x + i * (size + 6) + r, cy, r, fill, ring)


def _draw_heart(draw, cx: float, cy: float, s: float) -> None:
    """Like icon: two lobes + bottom point."""
    fill = (255, 69, 0, 255)  # Reddit orange
    r = s * 0.5
    top = cy - r * 0.55
    draw.ellipse([cx - 2 * r, top - r, cx, top + r], fill=fill)
    draw.ellipse([cx, top - r, cx + 2 * r, top + r], fill=fill)
    draw.polygon(
        [(cx - 2 * r * 0.92, top + r * 0.55),
         (cx + 2 * r * 0.92, top + r * 0.55),
         (cx, cy + s * 1.15)],
        fill=fill,
    )


def _draw_comment_bubble(draw, x: float, y: float, w: float, h: float) -> None:
    """Comment icon: rounded speech bubble with a tail."""
    fill = (113, 118, 123, 255)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h / 3, fill=fill)
    draw.polygon(
        [(x + h * 0.35, y + h - 1), (x + h * 0.8, y + h - 1),
         (x + h * 0.5, y + h * 1.4)],
        fill=fill,
    )


def _draw_share_arrow(draw, cx: float, cy: float, s: float) -> None:
    """Share icon: diagonal arrow (↗) with a chevron head."""
    fill = (113, 118, 123, 255)
    d = s * 0.9
    width = max(3, int(s * 0.26))
    draw.line(
        [(cx - d * 0.55, cy + d * 0.55), (cx + d * 0.5, cy - d * 0.5)],
        fill=fill, width=width,
    )
    draw.line(
        [(cx - d * 0.05, cy - d * 0.55), (cx + d * 0.55, cy - d * 0.55)],
        fill=fill, width=width,
    )
    draw.line(
        [(cx + d * 0.55, cy - d * 0.55), (cx + d * 0.55, cy + d * 0.05)],
        fill=fill, width=width,
    )


def build_reddit_post_card(
    title: str,
    out_path: Path,
    handle: str = "r/gaming",
    upvotes: int = 4200,
    comments: int = 317,
    shares: int = 1200,
    awards: int = 3,
    width: int = CARD_WIDTH,
) -> Path:
    """Render the floating Reddit-style post card as a transparent PNG.

    The card is a clean, modern rounded rectangle meant to be overlaid on
    the upper-center of the full-screen gameplay background: avatar +
    subreddit/Twitter handle + verified badge + award emojis + bold post
    title/hook + like/comment/share metrics. Everything is drawn at 2x
    and downscaled for smooth (anti-aliased) edges.
    """
    from PIL import Image, ImageDraw

    scale = 2  # supersample for anti-aliased corners and icons
    pad = 44
    avatar_r = 36
    header_h = avatar_r * 2
    title_size = 46
    title_line_h = 60
    metric_size = 30
    handle_size = 36
    gap_header_title = 26
    gap_title_metrics = 24
    metrics_h = 46

    # All geometry/fonts are computed directly at the supersampled scale.
    def S(v: float) -> float:
        return v * scale

    title_font = _load_font(S(title_size))
    handle_font = _load_font(S(handle_size))
    metric_font = _load_font(S(metric_size))

    # Measure text with a scratch canvas.
    probe = Image.new("RGBA", (8, 8))
    probe_draw = ImageDraw.Draw(probe)
    inner_w = width - pad * 2
    title_lines = _wrap_text(probe_draw, title, title_font, S(inner_w))[:4]
    if not title_lines:
        title_lines = [""]

    height = (
        pad + header_h + gap_header_title
        + len(title_lines) * title_line_h
        + gap_title_metrics + metrics_h + pad
    )

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

    # --- Header row: avatar + handle + verified + awards -------------------
    cy = S(pad + avatar_r)
    ax = S(pad + avatar_r)
    draw.ellipse(
        [ax - S(avatar_r), cy - S(avatar_r), ax + S(avatar_r), cy + S(avatar_r)],
        fill=(255, 69, 0, 255),
    )
    avatar_font = _load_font(S(40))
    initial = _handle_initial(handle)
    init_bbox = draw.textbbox((0, 0), initial, font=avatar_font)
    draw.text(
        (ax - (init_bbox[2] - init_bbox[0]) / 2 - init_bbox[0],
         cy - (init_bbox[3] - init_bbox[1]) / 2 - init_bbox[1]),
        initial, font=avatar_font, fill=(255, 255, 255, 255),
    )

    text_x = S(pad + avatar_r * 2 + 18)
    handle_bbox = draw.textbbox((0, 0), handle, font=handle_font)
    draw.text((text_x, cy - S(18)), handle, font=handle_font, fill=dark)
    handle_w = handle_bbox[2] - handle_bbox[0]

    badge_r = 19
    _draw_verified_badge(draw, text_x + handle_w + S(badge_r + 10), cy, S(badge_r))

    _draw_awards(draw, text_x + handle_w + S(badge_r * 2 + 34), cy, min(awards, 4))

    # --- Bold post title / hook ---------------------------------------------
    y = S(pad + header_h + gap_header_title)
    for line in title_lines:
        draw.text((S(pad), y), line, font=title_font, fill=dark)
        y += S(title_line_h)

    # --- Like / comment / share metrics --------------------------------------
    y = S(pad + header_h + gap_header_title
          + len(title_lines) * title_line_h + gap_title_metrics + 20)
    mx = S(pad)
    _draw_heart(draw, mx + S(11), y + S(10), S(11))
    likes_w = draw.textlength(_format_count(upvotes), font=metric_font)
    draw.text((mx + S(30), y), _format_count(upvotes), font=metric_font, fill=muted)
    mx += S(30) + likes_w + S(30)
    _draw_comment_bubble(draw, mx, y - S(2), S(26), S(20))
    comments_w = draw.textlength(_format_count(comments), font=metric_font)
    draw.text((mx + S(36), y), _format_count(comments), font=metric_font, fill=muted)
    mx += S(36) + comments_w + S(30)
    _draw_share_arrow(draw, mx + S(11), y + S(10), S(18))
    draw.text((mx + S(30), y), _format_count(shares), font=metric_font, fill=muted)

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
) -> List[str]:
    """Assemble the full ffmpeg argv for the full-screen vertical render.

    Layout: gameplay fills the whole 1080x1920 frame; the Reddit post card
    floats upper-center and fades out after `card_duration` seconds (None
    keeps it pinned for the whole video); kinetic captions burn in dead
    center. Caption PNGs are rendered on the fly when not supplied.

    Duration: when `audio_duration` (the probed voiceover length) is
    given, the output runs exactly that plus VIDEO_TAIL_S so the audio
    and caption tracks share start/end timestamps and the punchline gets
    a tight resonance tail.
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

    inputs: List[str] = [
        settings.FFMPEG_BIN, "-y",
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
    if audio_duration is not None:
        duration = audio_duration + VIDEO_TAIL_S
    else:
        duration = max(1.0, captions[-1].end if captions else 3.0) + VIDEO_TAIL_S

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
