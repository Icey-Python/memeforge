"""Kinetic caption builder.

Short-form vertical videos show 1-2 words per caption frame, centered
in the middle of the vertical frame with a heavy stroke. This module
chunks a script (plus per-line TTS audio durations) into caption
frames; the compositor pre-renders each frame as a transparent PNG
(Pillow) and burns them in with ffmpeg `overlay` filters — no
`drawtext`/freetype dependency, so it works on any ffmpeg build.

Synchronization contract: `line_durations[i]` must be the *exact*
duration of `lines[i]`'s synthesized audio segment (as probed from the
file that the voiceover concatenation actually decodes — never padded).
The timeline lays lines back-to-back on those durations, so caption
windows and the concatenated audio stream start and end at the same
millisecond timestamps with zero cumulative drift. When the TTS engine
supplies word-level timings (`word_timings`), chunk starts snap to the
exact spoken-word timestamps for frame-accurate kinetic captions;
otherwise chunks are distributed proportionally to word count.
"""

import re
from typing import List, Optional

from pydantic import BaseModel

from app.providers.tts.base import WordTiming


class CaptionFrame(BaseModel):
    """One kinetic caption frame: 1-2 words shown for `duration` seconds."""

    words: str
    start: float  # seconds
    end: float  # seconds
    is_punchline: bool = False

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


_WORDS_PER_FRAME = 2


def _split_words(line: str) -> List[str]:
    return [w for w in re.split(r"\s+", line.strip()) if w]


def chunk_line(line: str, words_per_frame: int = _WORDS_PER_FRAME) -> List[str]:
    """Split a script line into caption chunks of 1-2 words."""
    words = _split_words(line)
    if not words:
        return []
    chunks = []
    for i in range(0, len(words), words_per_frame):
        chunks.append(" ".join(words[i : i + words_per_frame]))
    return chunks


def _usable_word_timings(
    timings: Optional[List[WordTiming]], words: List[str], line_duration: float
) -> Optional[List[WordTiming]]:
    """Validate engine word timings against the line before trusting them.

    The engine must report exactly one timing per script word (positional
    match), in order, inside the probed audio window. Anything else
    (expansions like "2" -> "two words", clipped metadata, ...) falls
    back to proportional distribution.
    """
    if not timings or len(timings) != len(words) or line_duration <= 0:
        return None
    prev_start = -1.0
    for timing in timings:
        if (
            not 0.0 <= timing.start < timing.end
            or timing.end > line_duration + 0.1  # small probe tolerance
            or timing.start < prev_start  # not monotonic
        ):
            return None
        prev_start = timing.start
    return timings


def _word_timed_frames(
    chunks: List[str],
    timings: List[WordTiming],
    line_start: float,
    line_duration: float,
    is_punch: bool,
) -> List[CaptionFrame]:
    """Caption frames driven by exact spoken-word timestamps.

    Each chunk appears exactly when its first word is spoken and holds
    until the next chunk starts (no flicker in inter-word gaps); the
    line's last chunk holds through the end of the line's audio segment
    so consecutive lines stay gapless.
    """
    line_end = line_start + line_duration
    words_per_chunk = [max(1, len(c.split())) for c in chunks]

    starts: List[float] = []
    pos = 0
    for count in words_per_chunk:
        first_word = timings[pos]
        starts.append(min(max(line_start + first_word.start, line_start), line_end))
        pos += count

    frames: List[CaptionFrame] = []
    for i, chunk in enumerate(chunks):
        last_word = timings[sum(words_per_chunk[: i + 1]) - 1]
        exact_end = min(line_start + last_word.end, line_end)
        if i + 1 < len(chunks):
            end = max(exact_end, starts[i + 1])
        else:
            end = line_end  # hold through the line's tail: gapless lines
        frames.append(
            CaptionFrame(
                words=chunk.upper(),
                start=round(starts[i], 3),
                end=round(min(max(end, starts[i]), line_end), 3),
                is_punchline=is_punch,
            )
        )
    return frames


def _proportional_frames(
    chunks: List[str],
    line_start: float,
    line_duration: float,
    is_punch: bool,
) -> List[CaptionFrame]:
    """Caption frames spread proportionally to word count within the line.

    Chunk boundaries are rounded once and the cursor advances on the
    rounded value, so consecutive frames tile the line exactly (no
    sub-millisecond seams) and the line ends at its audio boundary.
    """
    weights = [max(1, len(c.split())) for c in chunks]
    weight_sum = float(sum(weights))
    line_end = line_start + line_duration
    frames: List[CaptionFrame] = []
    cursor = line_start
    for i, (chunk, weight) in enumerate(zip(chunks, weights)):
        chunk_dur = line_duration * (weight / weight_sum)
        if i + 1 < len(chunks):
            end = round(min(cursor + chunk_dur, line_end), 3)
        else:
            end = round(line_end, 3)
        frames.append(
            CaptionFrame(
                words=chunk.upper(),
                start=round(cursor, 3),
                end=end,
                is_punchline=is_punch,
            )
        )
        cursor = end
    return frames


def build_caption_timeline(
    lines: List[str],
    line_durations: List[float],
    punchline_indexes: set | None = None,
    total_duration: float | None = None,
    word_timings: Optional[List[Optional[List[WordTiming]]]] = None,
) -> List[CaptionFrame]:
    """Build the full caption timeline for a video.

    `line_durations[i]` is the exact probed TTS duration of `lines[i]` in
    seconds (unpadded); lines are laid back-to-back so the timeline
    matches the concatenated voiceover sample-for-sample. When
    `word_timings[i]` carries engine word timestamps for the line, chunk
    boundaries snap to exact spoken-word times; otherwise chunks are
    distributed proportionally to word count.

    If `total_duration` is given (the probed duration of the final
    concatenated voiceover), any leftover time is appended to the last
    frame so the caption track ends exactly with the audio track.
    """
    if len(lines) != len(line_durations):
        raise ValueError(
            f"lines ({len(lines)}) and line_durations ({len(line_durations)}) "
            "must have the same length"
        )
    if word_timings is not None and len(word_timings) != len(lines):
        raise ValueError(
            f"word_timings ({len(word_timings)}) must align with lines "
            f"({len(lines)}); use None entries for lines without timings"
        )
    punchline_indexes = punchline_indexes or set()

    frames: List[CaptionFrame] = []
    cursor = 0.0  # audio-exact: cumulative start of the current line
    for idx, (line, duration) in enumerate(zip(lines, line_durations)):
        chunks = chunk_line(line)
        if not chunks:
            continue
        is_punch = idx in punchline_indexes
        timings = None
        if word_timings is not None:
            timings = _usable_word_timings(
                word_timings[idx], _split_words(line), duration
            )
        if timings is not None:
            frames.extend(
                _word_timed_frames(chunks, timings, cursor, duration, is_punch)
            )
        else:
            frames.extend(_proportional_frames(chunks, cursor, duration, is_punch))
        cursor += duration

    if total_duration is not None and frames and cursor < total_duration:
        # stretch the last frame to cover the tail of the video
        frames[-1].end = round(total_duration, 3)

    return frames
