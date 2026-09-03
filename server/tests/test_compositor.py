"""Compositor unit tests: full-screen layout, floating card, caption PNGs,
random background seek.

Regression guard: the render pipeline must not depend on ffmpeg's optional
`drawtext` filter (absent from Homebrew builds). Captions are Pillow PNGs
burned in via `overlay`. The background loop must fill the whole 1080x1920
frame (no vstack / 50-50 split), with the headline card floating
upper-center and captions centered in the middle of the frame. Long
background assets get a random `-ss` in-point before the input loop.
"""

import random
from pathlib import Path

import pytest
from PIL import Image

from app.core import settings
from app.providers.tts.base import WordTiming
from app.services.rendering.captions import build_caption_timeline
from app.services.rendering.compositor import (
    CARD_TOP_FRACTION,
    CARD_WIDTH,
    SEEK_MARGIN_S,
    VIDEO_TAIL_S,
    build_headline_card,
    compose_video,
    compute_background_seek,
    concat_audio_args,
    duration_from_probe,
    final_cut_duration,
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


def test_build_headline_card(tmp_path: Path):
    out = build_headline_card(
        "You are NOT ready for this Elden Ring take",
        tmp_path / "card.png",
        style="hook",
    )

    assert out.exists() and out.stat().st_size > 2_000
    with Image.open(out) as im:
        assert im.mode == "RGBA"  # transparent corners → floats over background
        assert im.width == CARD_WIDTH
        assert im.height > 100
        # Rounded corner: top-left pixel transparent.
        assert im.getpixel((2, 2))[3] == 0
        # Card body: near-opaque white in the middle of the first text row.
        assert im.getpixel((CARD_WIDTH // 2, 60))[3] > 200


def test_build_headline_card_wraps_long_titles(tmp_path: Path):
    short = build_headline_card("Short one", tmp_path / "short.png")
    long = build_headline_card(
        "This is an extremely long post title that absolutely has to wrap "
        "across multiple lines inside the floating card",
        tmp_path / "long.png",
    )
    with Image.open(short) as s, Image.open(long) as l:
        assert l.height > s.height  # wrapped title grows the card


def test_build_headline_card_quote_style(tmp_path: Path):
    hook = build_headline_card(
        "quote me on this", tmp_path / "hook.png", style="hook"
    )
    quote = build_headline_card(
        "quote me on this", tmp_path / "quote.png", style="quote"
    )

    assert quote.exists() and quote.stat().st_size > 2_000
    with Image.open(hook) as h, Image.open(quote) as q:
        assert q.mode == "RGBA"
        assert q.width == CARD_WIDTH
        # The oversized quote mark adds height on top of the text block.
        assert q.height > h.height


def test_build_headline_card_rejects_unknown_style(tmp_path: Path):
    with pytest.raises(ValueError, match="card style"):
        build_headline_card("nope", tmp_path / "bad.png", style="nope")


# --- Random seek in-point for long background assets ------------------------


def test_compute_background_seek_long_clip():
    """A 5-120min asset gets a random in-point that leaves headroom."""
    rng = random.Random(0)
    # 600s b-roll, 60s requested: seek ∈ [0, 600-60-1].
    for _ in range(50):
        seek = compute_background_seek(600.0, 60.0, rng=rng)
        assert seek is not None
        assert 0.0 <= seek <= 600.0 - 60.0 - 1.0
        assert seek < 600.0 - 60.0  # never eats into the tail headroom


def test_compute_background_seek_short_clip_is_none():
    """Tight clips/loops play from the top; only long assets seek."""
    # Exactly at the margin boundary: 65 <= 60 + 5 → no seek.
    assert compute_background_seek(65.0, 60.0) is None
    # A 10s loop for a 60s video: loops from the top.
    assert compute_background_seek(10.0, 60.0) is None
    # Degenerate durations.
    assert compute_background_seek(0.0, 60.0) is None
    assert compute_background_seek(600.0, 0.0) is None


def test_compute_background_seek_is_deterministic_with_seed():
    a = compute_background_seek(600.0, 60.0, rng=random.Random(42))
    b = compute_background_seek(600.0, 60.0, rng=random.Random(42))
    assert a == b
    assert a is not None and a > 0.0


def test_compute_background_seek_uses_default_rng():
    """Without an injected rng the global random module is used."""
    seek = compute_background_seek(600.0, 60.0)
    assert seek is not None
    assert 0.0 <= seek <= 600.0 - 60.0 - 1.0


def test_compose_video_random_seek_before_input_loop(tmp_path: Path):
    """-ss lands before -stream_loop -i so the background starts at the
    random in-point (fresh footage per render)."""
    frames, argv = _compose(tmp_path, background_seek=123.456)

    assert "-ss" in argv
    ss = argv.index("-ss")
    loop = argv.index("-stream_loop")
    gameplay_at = argv.index(str(Path("gameplay.mp4")))
    assert ss < loop < gameplay_at  # input option order: -ss … -stream_loop … -i
    assert argv[ss + 1] == "123.456"


def test_compose_video_no_seek_by_default(tmp_path: Path):
    """Tight clips and unprobed assets render from the top: no -ss."""
    _, argv = _compose(tmp_path)
    assert "-ss" not in argv


def test_final_cut_duration():
    frames = _frames()
    # Probed audio drives the cut: audio + tight tail.
    assert final_cut_duration(frames, 6.5) == pytest.approx(6.5 + VIDEO_TAIL_S)
    # No probe: the caption end drives the cut.
    expected = frames[-1].end + VIDEO_TAIL_S
    assert final_cut_duration(frames, None) == pytest.approx(expected)
    # Empty captions without a probe still produce a renderable cut
    # (the original 3.0s fallback).
    assert final_cut_duration([], None) == pytest.approx(3.0 + VIDEO_TAIL_S)


def test_compose_video_background_seek_with_margin_rule():
    """The renderer only seeks when the clip outlasts the cut by > 5s."""
    assert SEEK_MARGIN_S == 5.0


# --- Audio/caption synchronization -------------------------------------------


def test_caption_timeline_tracks_probed_durations_exactly():
    """Line windows are the probed audio segments, back to back.

    Regression guard for the ~2.8s cumulative drift: no synthetic per-line
    padding may creep into the caption timeline, and frames must tile the
    full voiceover with no gaps or overlaps.
    """
    lines = ["one two three", "four five six seven", "eight"]
    durations = [1.2, 2.0, 0.8]

    frames = build_caption_timeline(lines, durations)

    # Line starts are the cumulative sum of exact probed durations.
    line_starts = [0.0, 1.2, 3.2]
    for start in line_starts:
        kicked = [f for f in frames if abs(f.start - start) < 0.001]
        assert kicked, f"no caption frame starts at line boundary {start}"
    # Frames tile the timeline exactly: gapless, no overlap, no dead space.
    assert frames[0].start == 0.0
    assert frames[-1].end == pytest.approx(sum(durations), abs=1e-6)
    for prev, nxt in zip(frames, frames[1:]):
        assert nxt.start == pytest.approx(prev.end, abs=1e-6)
    # No per-line padding: 3 lines must NOT add 3 * 0.35s of phantom tail.
    assert sum(durations) == pytest.approx(4.0)
    assert frames[-1].end == pytest.approx(4.0, abs=1e-6)


def test_caption_timeline_word_timings_exact_starts():
    """Word-boundary timings snap chunk starts to spoken-word timestamps."""
    lines = ["brace yourself gamers"]
    durations = [2.0]
    timings = [
        [
            WordTiming(text="brace", start=0.10, end=0.40),
            WordTiming(text="yourself", start=0.45, end=0.95),
            WordTiming(text="gamers", start=1.00, end=1.60),
        ]
    ]

    frames = build_caption_timeline(
        lines, durations, word_timings=timings, total_duration=2.0
    )

    assert [f.words for f in frames] == ["BRACE YOURSELF", "GAMERS"]
    # Exact spoken-word starts (not even proportional splits).
    assert frames[0].start == pytest.approx(0.10, abs=1e-6)
    assert frames[1].start == pytest.approx(1.00, abs=1e-6)
    # Chunk holds until the next starts; last chunk holds to line end.
    assert frames[0].end == pytest.approx(1.00, abs=1e-6)
    assert frames[1].end == pytest.approx(2.00, abs=1e-6)
    # Gapless after the first spoken word: no dead space between chunks.
    for prev, nxt in zip(frames, frames[1:]):
        assert nxt.start == pytest.approx(prev.end, abs=1e-6)


def test_caption_timeline_word_timings_offset_by_line_start():
    """Timings are line-relative; line 2's frames offset by line 1's audio."""
    lines = ["first line here", "second line now"]
    durations = [1.5, 2.0]
    timings = [
        [
            WordTiming(text="first", start=0.05, end=0.30),
            WordTiming(text="line", start=0.35, end=0.60),
            WordTiming(text="here", start=0.65, end=0.95),
        ],
        [
            WordTiming(text="second", start=0.08, end=0.50),
            WordTiming(text="line", start=0.55, end=0.80),
            WordTiming(text="now", start=0.85, end=1.20),
        ],
    ]

    frames = build_caption_timeline(lines, durations, word_timings=timings)

    line2_frames = [f for f in frames if f.words in ("SECOND LINE", "NOW")]
    assert line2_frames[0].start == pytest.approx(1.5 + 0.08, abs=1e-6)
    assert line2_frames[-1].end == pytest.approx(3.5, abs=1e-6)  # line 2 end


def test_caption_timeline_word_timings_mismatch_falls_back():
    """Engine timings that don't match the script degrade to proportional."""
    lines = ["two words"]
    durations = [1.0]
    # 3 timings for 2 script words (e.g. number expansion) -> unusable.
    bad = [[
        WordTiming(text="two", start=0.0, end=0.2),
        WordTiming(text="words", start=0.3, end=0.5),
        WordTiming(text="extra", start=0.6, end=0.8),
    ]]
    frames = build_caption_timeline(lines, durations, word_timings=bad)
    # Proportional fallback: single chunk tiles the whole line.
    assert len(frames) == 1
    assert frames[0].start == 0.0 and frames[0].end == pytest.approx(1.0)

    # Non-monotonic timings are equally rejected.
    bad_order = [[
        WordTiming(text="two", start=0.5, end=0.8),
        WordTiming(text="words", start=0.1, end=0.4),
    ]]
    frames = build_caption_timeline(lines, durations, word_timings=bad_order)
    assert frames[0].start == 0.0 and frames[0].end == pytest.approx(1.0)


def test_caption_timeline_validates_word_timings_shape():
    with pytest.raises(ValueError, match="word_timings"):
        build_caption_timeline(
            ["a"], [1.0], word_timings=[None, None]
        )


def test_caption_timeline_stretches_last_frame_to_audio_total():
    """Final-encode leftovers are absorbed so captions end with the audio."""
    lines = ["one two three four"]
    durations = [2.0]
    frames = build_caption_timeline(
        lines, durations, total_duration=2.026  # mp3/aac frame rounding
    )
    assert frames[-1].end == pytest.approx(2.026, abs=1e-6)


def test_compose_video_audio_padded_to_full_cut(tmp_path: Path):
    """The audio track spans the whole video so the SFX rings through
    the tail instead of being truncated at the voiceover's end."""
    # No-SFX path: plain pad to the full cut.
    _, argv = _compose(tmp_path, audio_duration=6.5)
    graph = _graph(argv)
    assert f"apad=whole_dur={6.5 + VIDEO_TAIL_S:.3f}" in graph

    # SFX path: mixed with duration=longest, then padded to the full cut.
    _, argv = _compose(
        tmp_path, audio_duration=6.5,
        sfx_path=Path("boom.mp3"), sfx_events=[5.0],
    )
    graph = _graph(argv)
    assert "amix=inputs=2:duration=longest:dropout_transition=0" in graph
    assert "volume=1.5,apad=whole_dur=6.800[a]" in graph


def test_compose_video_duration_is_audio_plus_tight_tail(tmp_path: Path):
    """Final cut = exact voiceover duration + 0.3s, nothing looser."""
    frames, argv = _compose(tmp_path, audio_duration=6.5)
    assert argv[argv.index("-t") + 1] == f"{6.5 + VIDEO_TAIL_S:.3f}"
    assert VIDEO_TAIL_S == 0.3


def test_compose_video_duration_falls_back_to_captions(tmp_path: Path):
    """Without a probed audio length, the caption end drives the cut."""
    frames, argv = _compose(tmp_path, audio_duration=None)
    expected = frames[-1].end + VIDEO_TAIL_S
    assert argv[argv.index("-t") + 1] == f"{expected:.3f}"


def test_caption_timeline_tiles_exactly_with_ugly_floats():
    """Rounded boundaries never open sub-millisecond seams between frames."""
    lines = ["alpha beta gamma delta epsilon", "zeta eta theta iota kappa"]
    durs = [1.733, 2.419]  # probed values are never round
    frames = build_caption_timeline(
        lines, durs, total_duration=sum(durs)
    )

    assert frames[0].start == 0.0
    # Line boundary lands exactly at the cumulative probed duration.
    assert any(f.start == 1.733 for f in frames)
    assert frames[-1].end == pytest.approx(4.152, abs=1e-9)
    for prev, nxt in zip(frames, frames[1:]):
        assert nxt.start == prev.end  # byte-exact, not approx


# --- Voiceover concatenation (sample-exact, gapless) --------------------------


def test_concat_audio_args_gapless_concat_filter():
    argv = concat_audio_args(
        [Path("a.mp3"), Path("b.mp3"), Path("c.mp3")], Path("out.wav")
    )
    graph = argv[argv.index("-filter_complex") + 1]

    # Decoded + resampled concat filter: boundaries land at exactly the
    # sum of probed per-part durations.
    assert "concat=n=3:v=0:a=1[a]" in graph
    assert argv[argv.index("-map") + 1] == "[a]"
    # Sample-exact PCM output (no mp3 frame rounding on the voiceover).
    assert "pcm_s16le" in argv
    assert str(Path("out.wav")) in argv
    # Gapless by default: no injected silence anywhere.
    assert "anullsrc" not in " ".join(argv)
    assert "lavfi" not in " ".join(argv)


def test_concat_audio_args_optional_pacing_gap():
    argv = concat_audio_args(
        [Path("a.mp3"), Path("b.mp3")], Path("out.wav"), gap_ms=150
    )
    graph = argv[argv.index("-filter_complex") + 1]

    # Exactly one silence source between the two parts, timed to the ms.
    assert argv.count("-i") == 3
    lavfi = argv.index("-f")
    assert argv[lavfi + 1] == "lavfi"
    assert argv[lavfi + 2] == "-t" and argv[lavfi + 3] == "0.150"
    assert "anullsrc=r=44100:cl=mono" in argv
    assert "concat=n=3:v=0:a=1[a]" in graph


def test_concat_audio_args_single_part_passthrough():
    argv = concat_audio_args([Path("a.mp3")], Path("out.wav"))
    graph = argv[argv.index("-filter_complex") + 1]

    # No concat filter for a single part — just normalize + re-encode.
    assert "concat=" not in graph
    assert graph.startswith("[0:a]aresample=44100,")
    assert graph.endswith("[a]")


def test_concat_audio_args_requires_parts():
    with pytest.raises(ValueError, match="no audio parts"):
        concat_audio_args([], Path("out.wav"))


# --- Exact duration probing ----------------------------------------------------


def test_duration_from_probe_prefers_stream_duration():
    # The audio stream's duration is decoded-frame/sample accurate.
    payload = (
        '{"streams": [{"duration": "1.000"}], '
        '"format": {"duration": "2.000"}}'
    )
    assert duration_from_probe(payload) == pytest.approx(1.0)


def test_duration_from_probe_falls_back_to_container():
    payload = '{"streams": [{}], "format": {"duration": "1.234"}}'
    assert duration_from_probe(payload) == pytest.approx(1.234)


def test_duration_from_probe_rejects_garbage():
    assert duration_from_probe("not json") is None
    assert duration_from_probe('{"streams": [], "format": {}}') is None
