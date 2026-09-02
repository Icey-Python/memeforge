"""Compositor unit tests: full-screen layout, floating card, caption PNGs.

Regression guard: the render pipeline must not depend on ffmpeg's optional
`drawtext` filter (absent from Homebrew builds). Captions are Pillow PNGs
burned in via `overlay`. The gameplay loop must fill the whole 1080x1920
frame (no vstack / 50-50 split), with the Reddit post card floating
upper-center and captions centered in the middle of the frame.
"""

from pathlib import Path

from PIL import Image

from app.core import settings
from app.services.rendering.captions import build_caption_timeline
from app.services.rendering.compositor import (
    CARD_TOP_FRACTION,
    CARD_WIDTH,
    build_reddit_post_card,
    compose_video,
    render_caption_pngs,
)


def _frames():
    return build_caption_timeline(
        ["unpopular opinion inbound", "and that's why we can't have nice things"],
        [2.0, 2.5],
        punchline_indexes={1},
    )


def _compose(tmp_path: Path, **overrides):
    """compose_video argv for the default happy path (card + captions)."""
    frames = _frames()
    pngs = render_caption_pngs(frames, tmp_path)
    kwargs = dict(
        gameplay_path=Path("gameplay.mp4"),
        voiceover_path=Path("voiceover.mp3"),
        captions=frames,
        output_path=tmp_path / "out.mp4",
        card_path=Path("card.png"),
        caption_pngs=pngs,
        card_duration=4.0,
    )
    kwargs.update(overrides)
    return frames, compose_video(**kwargs)


def _graph(argv) -> str:
    return argv[argv.index("-filter_complex") + 1]


def test_caption_pngs_render(tmp_path: Path):
    frames = _frames()
    pngs = render_caption_pngs(frames, tmp_path)

    assert len(pngs) == len(frames)
    for png in pngs:
        assert png.exists() and png.stat().st_size > 0
    # Full-frame-width canvases, ready for dead-center overlaying.
    with Image.open(pngs[0]) as im:
        assert im.width == settings.VIDEO_WIDTH


def test_compose_video_fullscreen_background(tmp_path: Path):
    _, argv = _compose(tmp_path)
    graph = _graph(argv)

    # Gameplay fills the full 1080x1920 vertical frame, edge to edge.
    assert (
        f"scale={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT}"
        ":force_original_aspect_ratio=increase" in graph
    )
    assert f"crop={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT}," in graph
    # No split-screen / static top section anymore.
    assert "vstack" not in graph
    # Captions burn in via overlay with timed enables, never drawtext.
    assert "drawtext" not in graph


def test_compose_video_card_overlay_upper_center_with_fade(tmp_path: Path):
    _, argv = _compose(tmp_path)
    graph = _graph(argv)

    # Card fades in, holds through the hook, then fades out.
    assert "format=rgba" in graph
    assert "fade=t=in:st=0" in graph
    assert "alpha=1" in graph
    fade_out = f"fade=t=out:st={4.0 - 0.6:.3f}:d=0.6:alpha=1"
    assert fade_out in graph
    # Card floats in the upper-center region (~15% from top).
    assert f"y=main_h*{CARD_TOP_FRACTION}" in graph


def test_compose_video_card_pinned_when_no_duration(tmp_path: Path):
    _, argv = _compose(tmp_path, card_duration=None)
    graph = _graph(argv)

    # Pinned card: fades in but never fades out.
    assert "fade=t=in:st=0" in graph
    assert "fade=t=out" not in graph


def test_compose_video_captions_centered(tmp_path: Path):
    frames, argv = _compose(tmp_path)
    graph = _graph(argv)

    # One overlay per caption frame + one for the floating card.
    assert graph.count("overlay=") == len(frames) + 1
    assert graph.count("enable='between(t,") == len(frames)
    # Captions sit dead-center of the vertical frame (both axes).
    assert "x=(main_w-overlay_w)/2" in graph
    assert "y=(main_h-overlay_h)/2" in graph


def test_compose_video_input_indices(tmp_path: Path):
    frames, argv = _compose(
        tmp_path, sfx_path=Path("boom.mp3"), sfx_events=[1.0]
    )
    graph = _graph(argv)

    # 0: gameplay, 1: card, 2: voiceover, 3: sfx, 4+: captions.
    assert "[1:v]format=rgba" in graph
    assert "[2:a]aresample=44100[vo]" in graph
    assert "[3:a]aresample=44100" in graph
    assert "adelay='1000:all=1'" in graph
    assert "[4:v]" in graph
    # Every caption PNG is wired in as an input at the expected index.
    assert argv.count("-i") == 4 + len(frames)  # bg + card + vo + sfx + caps
    assert str(Path("card.png")) in argv
    assert str(Path("boom.mp3")) in argv
    # The final video stream is mapped as usual.
    assert "-map" in argv and "[v]" in argv


def test_compose_video_without_card(tmp_path: Path):
    frames, argv = _compose(tmp_path, card_path=None)
    graph = _graph(argv)

    assert "fade" not in graph
    assert graph.count("overlay=") == len(frames)
    # 0: gameplay, 1: voiceover, 2+: captions.
    assert "[bg][2:v]overlay" in graph


def test_compose_video_without_captions_or_card(tmp_path: Path):
    argv = compose_video(
        gameplay_path=Path("gameplay.mp4"),
        voiceover_path=Path("voiceover.mp3"),
        captions=[],
        output_path=tmp_path / "out.mp4",
        card_path=None,
    )
    graph = _graph(argv)

    # Nothing overlays the background: the video chain's [bg] is final [v].
    assert "overlay" not in graph
    assert graph.split(";")[0].endswith("[v]")
    assert (
        f"scale={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT}"
        ":force_original_aspect_ratio=increase,"
        f"crop={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT}" in graph
    )


def test_build_reddit_post_card(tmp_path: Path):
    out = build_reddit_post_card(
        "You are NOT ready for this Elden Ring take, gamers",
        tmp_path / "card.png",
        handle="r/gaming",
        upvotes=45_200,
        comments=891,
        shares=3_400,
        awards=3,
    )

    assert out.exists() and out.stat().st_size > 2_000
    with Image.open(out) as im:
        assert im.mode == "RGBA"  # transparent corners → floats over gameplay
        assert im.width == CARD_WIDTH
        assert im.height > 200
        # Rounded corner: top-left pixel transparent.
        assert im.getpixel((2, 2))[3] == 0
        # Card body: near-opaque white in the middle of the header row.
        assert im.getpixel((CARD_WIDTH // 2, 10))[3] > 200


def test_build_reddit_post_card_wraps_long_titles(tmp_path: Path):
    short = build_reddit_post_card("Short one", tmp_path / "short.png")
    long = build_reddit_post_card(
        "This is an extremely long post title that absolutely has to wrap "
        "across multiple lines inside the floating card",
        tmp_path / "long.png",
    )
    with Image.open(short) as s, Image.open(long) as l:
        assert l.height > s.height  # wrapped title grows the card
