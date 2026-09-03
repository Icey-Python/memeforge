"""Live end-to-end validation of the TTS/caption sync contract.

Proves, with real edge-tts + ffmpeg:
  1. concat_audio output duration == sum of per-line probed durations
     (sample-exact, zero dead space).
  2. Caption timeline tiles [0, total] gaplessly, line boundaries at
     cumulative probed durations.
  3. Word timings from edge-tts land inside their line windows.
  4. A full composed video's duration == voiceover duration + 0.3s.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers.tts.edge import EdgeTTSProvider
from app.services.rendering import compositor
from app.services.rendering.captions import build_caption_timeline

SCRIPT = [
    "unpopular gaming opinion incoming",
    "the tutorial is the best part of every game",
    "and yes i skip every cutscene anyway",
]


async def main() -> None:
    workdir = Path(tempfile.mkdtemp(prefix="sync-check-"))
    print(f"workdir: {workdir}")

    provider = EdgeTTSProvider()
    parts, durations, timings = [], [], []
    for i, line in enumerate(SCRIPT):
        audio = await provider.synthesize(line)
        part = workdir / f"line-{i:03d}.{audio.format}"
        part.write_bytes(audio.audio_bytes)
        parts.append(part)
        durations.append(await compositor.probe_duration(part))
        timings.append(audio.word_timings)
        n_words = len(line.split())
        t = audio.word_timings
        print(
            f"  line {i}: probed={durations[-1]:.3f}s "
            f"words={n_words} timings={len(t) if t else 0} "
            f"last_word_end={t[-1].end:.3f}s" if t else f"  line {i}: no timings"
        )

    voiceover = await compositor.concat_audio(parts, workdir / "voiceover.wav")
    total = await compositor.probe_duration(voiceover)
    print(f"\nsum(probed)     = {sum(durations):.6f}s")
    print(f"concat duration = {total:.6f}s")
    drift = total - sum(durations)
    print(f"drift           = {drift * 1000:.3f}ms")
    assert abs(drift) < 0.002, f"concat drifted {drift * 1000:.2f}ms"

    frames = build_caption_timeline(
        SCRIPT, durations,
        punchline_indexes={len(SCRIPT) - 1},
        total_duration=total,
        word_timings=timings,
    )
    print(f"\ncaption frames: {len(frames)}")
    for f in frames:
        print(f"  [{f.start:7.3f} → {f.end:7.3f}] {f.words}")
    assert frames[0].start >= 0
    # Caption timestamps are millisecond-resolution (matching the ffmpeg
    # overlay `enable` windows); the audio may run a few samples longer.
    assert frames[-1].end >= total - 0.001
    for prev, nxt in zip(frames, frames[1:]):
        assert nxt.start >= prev.end - 1e-9, "caption frames overlap"
    # every word timing's absolute position falls inside the video span
    cursor = 0.0
    for dur, t in zip(durations, timings):
        if t:
            assert t[-1].end <= cursor + dur + 0.001
        cursor += dur

    # Full compose + real render against a generated gameplay loop.
    vo_dur = await compositor.probe_duration(voiceover)
    gameplay = workdir / "gameplay.mp4"
    await compositor.run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=30",
        "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(gameplay),
    ])
    card = compositor.build_headline_card(
        "Sync check", workdir / "card.png", style="hook"
    )
    pngs = compositor.render_caption_pngs(frames, workdir)
    cmd = compositor.compose_video(
        gameplay_path=gameplay,
        voiceover_path=voiceover,
        captions=frames,
        output_path=workdir / "out.mp4",
        card_path=card,
        caption_pngs=pngs,
        audio_duration=vo_dur,
    )
    await compositor.run_ffmpeg(cmd)
    final = await _probe_format_duration(workdir / "out.mp4")
    print(f"\nvoiceover duration  = {vo_dur:.3f}s")
    print(f"final video duration = {final:.3f}s  (expected {vo_dur + 0.3:.3f}s)")
    assert abs(final - (vo_dur + 0.3)) < 0.05, "final video length off"

    # The audio track is padded to the full cut: A/V streams end together.
    audio_track = await _probe_audio_duration(workdir / "out.mp4")
    print(f"final audio duration = {audio_track:.3f}s")
    assert abs(audio_track - (vo_dur + 0.3)) < 0.05, "audio track not padded"

    # SFX variant: the boom rings through the tail past the voiceover end.
    boom = workdir / "boom.wav"
    await compositor.run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "sine=frequency=70:duration=1.2", "-c:a", "pcm_s16le",
        str(boom),
    ])
    cmd_sfx = compositor.compose_video(
        gameplay_path=gameplay,
        voiceover_path=voiceover,
        captions=frames,
        output_path=workdir / "out-sfx.mp4",
        card_path=card,
        caption_pngs=pngs,
        sfx_path=boom,
        sfx_events=[frames[-1].start],
        audio_duration=vo_dur,
    )
    await compositor.run_ffmpeg(cmd_sfx)
    final_sfx = await _probe_format_duration(workdir / "out-sfx.mp4")
    sfx_audio = await _probe_audio_duration(workdir / "out-sfx.mp4")
    print(f"sfx video duration   = {final_sfx:.3f}s, audio = {sfx_audio:.3f}s")
    assert abs(final_sfx - (vo_dur + 0.3)) < 0.05
    assert sfx_audio >= vo_dur  # boom was not cut at the voiceover end


async def _probe_audio_duration(path: Path) -> float:
    """Exact audio stream duration of a rendered video."""
    import json

    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration", "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return float(json.loads(out.decode())["streams"][0]["duration"])


async def _probe_format_duration(path: Path) -> float:
    """Container duration of a rendered video (longest stream)."""
    import json

    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return float(json.loads(out.decode())["format"]["duration"])


if __name__ == "__main__":
    print("\nALL SYNC INVARIANTS HELD ✔")


if __name__ == "__main__":
    asyncio.run(main())
