"""Kinetic caption builder.

Reddit-style shorts show 1-2 words per caption frame, centered on screen
with a heavy stroke. This module chunks a script (plus per-line TTS audio
durations) into caption frames; the compositor pre-renders each frame as a
transparent PNG (Pillow) and burns them in with ffmpeg `overlay` filters —
no `drawtext`/freetype dependency, so it works on any ffmpeg build.
"""

import re
from typing import List

from pydantic import BaseModel


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


def build_caption_timeline(
    lines: List[str],
    line_durations: List[float],
    punchline_indexes: set | None = None,
    total_duration: float | None = None,
) -> List[CaptionFrame]:
    """Build the full caption timeline for a video.

    `line_durations[i]` is the TTS duration of `lines[i]` in seconds.
    Frames are distributed proportionally to word count within each line.
    If total_duration is given, leftover time is appended to the last frame.
    """
    if len(lines) != len(line_durations):
        raise ValueError(
            f"lines ({len(lines)}) and line_durations ({len(line_durations)}) "
            "must have the same length"
        )
    punchline_indexes = punchline_indexes or set()

    frames: List[CaptionFrame] = []
    cursor = 0.0
    for idx, (line, duration) in enumerate(zip(lines, line_durations)):
        chunks = chunk_line(line)
        if not chunks:
            continue
        is_punch = idx in punchline_indexes
        # weight each chunk by its word count for proportional timing
        weights = [max(1, len(c.split())) for c in chunks]
        weight_sum = float(sum(weights))
        chunk_start = cursor
        for chunk, weight in zip(chunks, weights):
            chunk_dur = duration * (weight / weight_sum)
            frames.append(
                CaptionFrame(
                    words=chunk.upper(),
                    start=round(chunk_start, 3),
                    end=round(chunk_start + chunk_dur, 3),
                    is_punchline=is_punch,
                )
            )
            chunk_start += chunk_dur
        cursor = chunk_start

    if total_duration is not None and frames and cursor < total_duration:
        # stretch the last frame to cover the tail of the video
        frames[-1].end = round(total_duration, 3)

    return frames
