"""LLM connector base class.

A provider turns a video topic into a short-form video script (list of
spoken lines). Implementations must be async so they can be awaited
directly inside FastAPI endpoints and background render jobs.

Duration pacing: scripts target a spoken length in seconds. At a ~140
wpm speaking pace that is ~2.2-2.5 words per second, so a 60-second
script lands at ~130-150 words — the standard for YouTube Shorts,
TikTok, and Reels. `word_target()` and `default_line_count()` convert a
duration target into those budgets.
"""

from typing import List, Optional, Tuple

from pydantic import BaseModel


# Spoken pace used to convert duration targets into word budgets
# (~140 wpm: 2.2 words/s is the floor, 2.5 words/s the ceiling).
_WORDS_PER_SEC_MIN = 2.2
_WORDS_PER_SEC_MAX = 2.5
# Rough line pacing: one short spoken line ≈ 4 seconds of speech.
_SECONDS_PER_LINE = 4.0


def word_target(duration_target: int) -> Tuple[int, int]:
    """(min_words, max_words) a script should hit for `duration_target` s.

    E.g. 60s → (132, 150): the classic ~130-150 word short-form pacing.
    """
    return (
        round(duration_target * _WORDS_PER_SEC_MIN),
        round(duration_target * _WORDS_PER_SEC_MAX),
    )


def default_line_count(duration_target: int) -> int:
    """Default max-lines budget for a duration target (~4s per line).

    E.g. 30s → 8 lines, 60s → 15 lines, 90s → 23 lines (capped at 40).
    """
    return max(5, min(40, round(duration_target / _SECONDS_PER_LINE)))


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
