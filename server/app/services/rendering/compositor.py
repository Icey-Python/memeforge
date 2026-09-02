"""FFmpeg split-screen compositor.

Builds and runs the ffmpeg command that turns (reddit card, gameplay loop,
voiceover, caption timeline) into a vertical 1080x1920 short:

    +------------------+  \
    |  Reddit-style    |  | top frame (1080x960): meme card image
    |  meme card       |  |
    +------------------+  / center: kinetic captions (1-2 words/frame,
    |                  |  \         heavy stroke, punchlines punch harder)
    |  Gameplay loop   |  | bottom frame (1080x1920): endless gameplay
    +------------------+  /

Captions are pre-rendered as transparent PNGs with Pillow and composited
with the `overlay` filter — deliberately avoiding `drawtext`, which needs
an ffmpeg built with libfreetype (Homebrew's is not). `moviepy` is an
acceptable alternative wrapper for complex effects; ffmpeg filter graphs
are used here because they are fast, dependency-light, and deterministic.

All ffmpeg/ffprobe calls run through asyncio subprocess (with timeouts)
so renders never block or hang the event loop.
"""

import asyncio
import shutil
from pathlib import Path
from typing import List, Optional, Sequence

from app.core import settings
from app.services.rendering.captions import CaptionFrame

# Caption look: huge bold text with a heavy black stroke.
CAPTION_FONT_SIZE = 108
CAPTION_STROKE_WIDTH = 12  # the "heavy stroke" meme aesthetic
CAPTION_COLOR = "white"
CAPTION_STROKE_COLOR = "black"
PUNCHLINE_COLOR = "FDE047"  # yellow pop on punchlines
PUNCHLINE_FONT_SIZE = 126

# Safety timeouts so a stalled network read or subprocess can't hang a job.
FFMPEG_TIMEOUT_S = 600.0
FFPROBE_TIMEOUT_S = 30.0


def _default_font() -> str:
    """Best-effort bundled/system bold font path for drawtext."""
    candidates = [
        settings.FONTS_DIR / "Inter-Bold.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),  # macOS
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),  # Debian
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),  # Arch
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return ""  # ffmpeg falls back to its built-in font


def ffmpeg_available() -> bool:
    return shutil.which(settings.FFMPEG_BIN) is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


async def probe_duration(media_path: Path) -> float:
    """Duration of an audio/video file in seconds, via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
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
    return float(stdout.decode().strip())


def build_reddit_card(
    title: str, topic: str, out_path: Path, upvotes: int = 42
) -> Path:
    """Render the Reddit-style meme card for the top frame.

    Uses Pillow; when the caller already has a card/screenshot, it can be
    passed to `compose_video` directly instead.
    """
    from PIL import Image, ImageDraw, ImageFont  # imported lazily

    width, height = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT // 2
    card = Image.new("RGB", (width, height), "#1A1A1B")
    draw = ImageDraw.Draw(card)

    font_candidates = [
        _default_font(),
        "DejaVuSans-Bold.ttf",
        "Arial Bold.ttf",
    ]
    title_font = None
    for cand in font_candidates:
        if not cand:
            continue
        try:
            title_font = ImageFont.truetype(cand, 52)
            meta_font = ImageFont.truetype(cand, 30)
            break
        except OSError:
            continue
    if title_font is None:
        title_font = ImageFont.load_default()
        meta_font = title_font

    # Upvote column + upvote count, r/gaming style.
    orange = "#FF4500"
    draw.rounded_rectangle(
        [48, 96, 128, 320], radius=16, fill="#272729", outline=orange, width=2
    )
    draw.polygon([(88, 130), (62, 175), (114, 175)], fill=orange)
    draw.polygon([(62, 240), (114, 240), (88, 285)], fill="#818384")
    draw.text((50, 330), f"{upvotes // 1000}k" if upvotes >= 1000 else str(upvotes),
              font=meta_font, fill="#D7DADC")

    # Subreddit + author meta line.
    draw.text((176, 110), f"r/gaming  ·  u/{topic.replace(' ', '_')[:24]}",
              font=meta_font, fill="#818384")

    # Title, wrapped to the card width.
    max_width = width - 176 - 64
    words, lines, cur = title.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=title_font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    y = 176
    for line in lines[:6]:
        draw.text((176, y), line, font=title_font, fill="#D7DADC")
        y += 68

    card.save(out_path, format="PNG")
    return out_path


def _load_caption_font(size: int):
    """Bold truetype font for captions; falls back to Pillow default."""
    from PIL import ImageFont

    candidates = [
        settings.FONTS_DIR / "Inter-Bold.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),  # macOS
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),  # Debian
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),  # Arch
    ]
    for cand in candidates:
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_caption_pngs(
    frames: Sequence[CaptionFrame], workdir: Path
) -> List[Path]:
    """Pre-render each caption frame as a transparent PNG (Pillow).

    Heavy stroke text centered on a full-width canvas; punchlines get the
    yellow pop. PNGs are later burned in with `overlay` filters, keeping
    the pipeline free of ffmpeg's optional drawtext filter.
    """
    from PIL import Image, ImageDraw

    pngs: List[Path] = []
    for i, frame in enumerate(frames):
        font = _load_caption_font(
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
) -> tuple[List[str], List[str]]:
    """Overlay filter snippets chaining the caption PNGs onto the video.

    Returns (filter_snippets, input_args). Each PNG enters as its own input
    and is overlaid centered on the gameplay half, visible only during its
    time window (`enable=between(t,...)`).
    """
    top_h = settings.VIDEO_HEIGHT // 2
    inputs: List[str] = []
    filters: List[str] = []
    prev = "[base]"
    for i, (png, frame) in enumerate(zip(caption_pngs, frames)):
        idx = first_input_index + i
        inputs += ["-i", str(png)]
        out = f"[cap{i}]" if i < len(caption_pngs) - 1 else "[v]"
        filters.append(
            f"{prev}[{idx}:v]overlay=x=0:"
            f"y={top_h + 40}:"
            f"enable='between(t,{frame.start:.3f},{frame.end:.3f})'{out}"
        )
        prev = out
    return filters, inputs


def compose_video(
    card_path: Path,
    gameplay_path: Path,
    voiceover_path: Path,
    captions: Sequence[CaptionFrame],
    output_path: Path,
    caption_pngs: Optional[Sequence[Path]] = None,
    workdir: Optional[Path] = None,
    sfx_path: Optional[Path] = None,
    sfx_events: Optional[List[float]] = None,
) -> List[str]:
    """Assemble the full ffmpeg argv for the split-screen render.

    Caption PNGs are rendered on the fly when not supplied (caller can pass
    pre-rendered ones from `render_caption_pngs`).
    """
    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    top_h = h // 2
    fps = settings.VIDEO_FPS

    if caption_pngs is None:
        if workdir is None:
            workdir = output_path.parent
        caption_pngs = render_caption_pngs(captions, workdir)

    inputs = [
        settings.FFMPEG_BIN, "-y",
        "-loop", "1", "-i", str(card_path),          # 0: reddit card
        "-stream_loop", "-1", "-i", str(gameplay_path),  # 1: gameplay loop
        "-i", str(voiceover_path),                   # 2: voiceover audio
    ]
    if sfx_path and sfx_events:
        inputs += ["-i", str(sfx_path)]              # 3: sfx (optional)

    # Video graph: scale both halves, vstack, burn captions on the gameplay.
    video_chain = (
        f"[0:v]scale={w}:{top_h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{top_h}[top];"
        f"[1:v]scale={w}:{top_h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{top_h},fps={fps},setsar=1[bottom];"
        f"[top][bottom]vstack=inputs=2[base]"
    )

    sfx_index = 3
    first_caption_index = 4 if (sfx_path and sfx_events) else 3
    caption_filters, caption_inputs = _caption_overlay_chain(
        caption_pngs, captions, first_caption_index
    )
    inputs += caption_inputs

    if not caption_pngs:
        # No captions: vstack output becomes the final video stream.
        video_chain = video_chain.replace("[base]", "[v]")

    parts = [video_chain]
    parts.extend(caption_filters)

    # Audio graph: voiceover (+ delayed sfx mixed in when provided).
    if sfx_path and sfx_events:
        delays = "|".join(f"{int(t * 1000)}:all=1" for t in sfx_events)
        parts.append(
            f"[2:a]aresample=44100[vo];"
            f"[{sfx_index}:a]aresample=44100,adelay='{delays}'[sfx];"
            f"[vo][sfx]amix=inputs=2:duration=first:dropout_transition=0,"
            "volume=1.5[a]"
        )
    else:
        parts.append("[2:a]aresample=44100[a]")

    filter_complex = ";".join(parts)

    # Duration: caption timeline end + a short tail so the punchline lands.
    duration = (
        max(1.0, captions[-1].end if captions else 3.0) + 0.6
    )

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


async def concat_audio(parts: List[Path], output: Path, gap_ms: int = 120) -> Path:
    """Concatenate per-line TTS audio with small breathing gaps."""
    if not parts:
        raise ValueError("no audio parts to concat")
    if len(parts) == 1 and gap_ms == 0:
        shutil.copyfile(parts[0], output)
        return output

    # Build a silent-gap file once, then use concat demuxer.
    gap = output.parent / "gap.mp3"
    gap_ms_total = gap_ms
    cmd = [
        settings.FFMPEG_BIN, "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", f"{gap_ms_total / 1000:.3f}",
        "-c:a", "libmp3lame", "-q:a", "4", str(gap),
    ]
    await run_ffmpeg(cmd)

    concat_list = output.parent / "concat.txt"
    lines = []
    for i, part in enumerate(parts):
        lines.append(f"file '{part.resolve()}'")
        if i < len(parts) - 1:
            lines.append(f"file '{gap.resolve()}'")
    concat_list.write_text("\n".join(lines), encoding="utf-8")

    await run_ffmpeg([
        settings.FFMPEG_BIN, "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "libmp3lame", "-q:a", "4", str(output),
    ])
    return output
