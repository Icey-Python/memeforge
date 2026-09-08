"""LLM connector base class.

A provider turns a video topic into a short-form video script (list of
spoken lines). Implementations must be async so they can be awaited
directly inside FastAPI endpoints and background render jobs.

Duration pacing: scripts target a spoken length in seconds. At a
~140-160 wpm speaking pace a 60-second script needs a full ~150 words
(135-165), 30s lands at 65-80, and 90s at 205-240 — the standard for
YouTube Shorts, TikTok, and Reels. `word_target()`,
`default_line_count()`, and `prompt_budget()` convert a duration
target into those budgets; the frontend mirrors the pace in
`web/src/lib/script-split.ts`.
"""

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel


# Word budgets for the studio duration presets (30/60/90 s). Spoken
# pace including TTS pauses and delivery tags lands at ~2.3-2.7
# words/sec, so a 60-second script needs a full ~150 words — enough
# speech to actually fill a minute of audio.
_WORD_BUDGETS: Dict[int, Tuple[int, int]] = {
    30: (65, 80),
    60: (135, 165),
    90: (205, 240),
}

# Fallback pacing for non-preset durations (~2.3-2.7 words/sec).
_WORDS_PER_SEC_MIN = 2.3
_WORDS_PER_SEC_MAX = 2.7
# Rough line pacing: one spoken sentence ≈ 4 seconds of speech.
_SECONDS_PER_LINE = 4.0

# Prompt-facing bands: LLMs drift short when given loose word ranges,
# so the system prompts phrase a tight inner band of the budget plus
# an explicit line range for the model to aim at.
_PROMPT_BUDGETS: Dict[int, Tuple[int, int, int, int]] = {
    30: (70, 80, 7, 9),
    60: (140, 160, 14, 17),
    90: (210, 230, 21, 25),
}


def word_target(duration_target: int) -> Tuple[int, int]:
    """(min_words, max_words) a script should hit for `duration_target` s.

    E.g. 60s → (135, 165): a full ~150 words of speech — the classic
    short-form pacing that fills a minute of TTS audio.
    """
    preset = _WORD_BUDGETS.get(duration_target)
    if preset is not None:
        return preset
    return (
        round(duration_target * _WORDS_PER_SEC_MIN),
        round(duration_target * _WORDS_PER_SEC_MAX),
    )


def default_line_count(duration_target: int) -> int:
    """Default max-lines budget for a duration target (~4s per line).

    E.g. 30s → 8 lines, 60s → 15 lines, 90s → 23 lines (capped at 40).
    """
    return max(5, min(40, int(duration_target / _SECONDS_PER_LINE + 0.5)))


def prompt_budget(duration_target: int) -> Tuple[int, int, int, int]:
    """(word_lo, word_hi, line_lo, line_hi) phrased into LLM prompts.

    E.g. 60s → 140-160 words across 14-17 lines: a tight inner band of
    `word_target` plus the line range the model should aim for —
    undershooting the budget ends the video early. Non-preset durations
    derive a band around the word_target midpoint.
    """
    preset = _PROMPT_BUDGETS.get(duration_target)
    if preset is not None:
        return preset
    w_min, w_max = word_target(duration_target)
    pad = max(1, (w_max - w_min) // 5)
    lines = default_line_count(duration_target)
    return (
        w_min + pad,
        w_max - pad,
        max(1, lines - max(1, lines // 10)),
        lines,
    )


class GeneratedScript(BaseModel):
    title: str
    lines: List[str]
    # Visual stock-video search phrases tied to the script content
    # (10+ when the connector supports them; the endpoint pads via the
    # offline heuristic when a model returns none).
    keywords: List[str] = []


class DiscoveredModel(BaseModel):
    """A model served by a provider endpoint (live discovery)."""

    id: str  # exact model name to send back to the provider
    label: str = ""  # display label for dropdowns
    size_bytes: Optional[int] = None
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    modified_at: Optional[str] = None
    available: bool = True


class BaseLLMProvider:
    """Contract for model connectors (OpenAI-compatible, Ollama, ...)."""

    name: str = "base"

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    async def generate_script(
        self, topic: str, tone: str = "casual-commenter", max_lines: int = 8,
        duration_target: int = 60,
    ) -> GeneratedScript:
        """Generate a short punchy script about `topic`.

        `duration_target` is the wanted spoken length in seconds; word
        budgets come from `word_target()`.
        """
        raise NotImplementedError

    async def list_models(self) -> List[DiscoveredModel]:
        """Discover the models this connector's endpoint currently serves.

        Powers `/api/v1/models/discover` (Ollama `/api/tags`, OpenAI-
        compatible `GET /models`). Raises on connectivity/HTTP errors;
        the endpoint reports those as `reachable: false`.
        """
        raise NotImplementedError

    async def complete_json(self, system: str, user: str) -> dict:
        """Single-shot JSON completion (system + user prompt).

        Used by utility prompts (e.g. the stock-search keyword
        extractor). Providers without a real model (mock) raise
        NotImplementedError so callers can fall back to heuristics.
        """
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Whether this connector has everything it needs to run."""
        return True
