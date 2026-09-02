"""Compositor unit tests: caption PNGs + overlay filter graph.

Regression guard: the render pipeline must not depend on ffmpeg's optional
`drawtext` filter (absent from Homebrew builds). Captions are Pillow PNGs
burned in via `overlay`.
"""

from pathlib import Path

from app.core import settings
from app.services.rendering.captions import CaptionFrame, build_caption_timeline
from app.services.rendering.compositor import compose_video, render_caption_pngs


def _frames():
    return build_caption_timeline(
        ["unpopular opinion inbound", "and that's why we can't have nice things"],
        [2.0, 2.5],
        punchline_indexes={1},
    )


def test_caption_pngs_render(tmp_path: Path):
    frames = _frames()
    pngs = render_caption_pngs(frames, tmp_path)

    assert len(pngs) == len(frames)
    for png in pngs:
        assert png.exists() and png.stat().st_size > 0


def test_compose_video_graph_uses_overlay_not_drawtext(tmp_path: Path):
    frames = _frames()
    pngs = render_caption_pngs(frames, tmp_path)

    argv = compose_video(
        card_path=Path("card.png"),
        gameplay_path=Path("gameplay.mp4"),
        voiceover_path=Path("voiceover.mp3"),
        captions=frames,
        output_path=tmp_path / "out.mp4",
        caption_pngs=pngs,
    )

    graph = argv[argv.index("-filter_complex") + 1]

    # Captions burn in via overlay with timed enables, never drawtext.
    assert "drawtext" not in graph
    assert graph.count("overlay=") == len(frames)
    assert graph.count("enable='between(t,") == len(frames)

    # The vstack output is explicitly labeled and consumed by the chain.
    assert "vstack=inputs=2[base]" in graph
    assert "[base][3:v]overlay" in graph
    assert graph.rstrip("a").endswith("[v]") or "[v];" in graph

    # Vertical geometry locked to settings.
    assert f"scale={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT // 2}" in graph


def test_compose_video_without_captions_labels_v(tmp_path: Path):
    argv = compose_video(
        card_path=Path("card.png"),
        gameplay_path=Path("gameplay.mp4"),
        voiceover_path=Path("voiceover.mp3"),
        captions=[],
        output_path=tmp_path / "out.mp4",
    )
    graph = argv[argv.index("-filter_complex") + 1]

    # No captions: vstack output is the final [v] stream directly.
    assert "vstack=inputs=2[v]" in graph
    assert "overlay" not in graph
