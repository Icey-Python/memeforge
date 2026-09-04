"""Mock LLM provider.

Deterministic, offline script generator used for local development and
tests so the pipeline works end-to-end without any model or API key.
Scripts are paced to the requested duration target (~2.2-2.5 words/sec
of speech), so a 60-second target yields ~130-150 words.
"""

import random
from typing import List

from app.providers.llm.base import (
    BaseLLMProvider,
    DiscoveredModel,
    GeneratedScript,
    word_target,
)

_OPENERS = [
    "Nobody asked, but here's the truth about",
    "POV: you just discovered",
    "The council has decided:",
    "Gamer fact nobody wanted:",
    "Unpopular opinion inbound:",
]

_BODY = [
    "First off, {topic} is not a phase, it's a lifestyle.",
    "My whole personality is basically {topic} at this point.",
    "I told my squad about {topic} and now none of them talk to me.",
    "They said {topic} builds character. They lied.",
    "Every day I wake up and choose {topic} violence.",
    "Nobody: ... Me: anyway, {topic}.",
    "Sleep is temporary, {topic} is forever.",
    "The tutorial never prepared me for {topic}.",
    "My search history is just {topic} and regret.",
    "I have three hobbies and all of them are {topic}.",
    "My therapist says I lean on {topic} too much.",
    "We do not talk about the {topic} incident.",
    "Studies show {topic} improves nothing except vibes.",
    "Half my screen time is {topic} content.",
    "Nobody warned me {topic} would be this expensive.",
    "{topic} walked so my sleep schedule could collapse.",
    "I would trade my lunch for {topic}, and I love lunch.",
    "Every group project needs one {topic} person. I'm it.",
    "My camera roll is nine thousand {topic} screenshots.",
    "The {topic} grind never stops, and neither do I.",
]

_CLOSERS = [
    "And that's why we can't have nice things.",
    "Skill issue. Undeniable. Unforgivable.",
    "Touch grass. Immediately.",
    "This message was brought to you by sleep deprivation.",
    "Anyway, back to the grind.",
]

# Visual stock-video search phrase templates for the keyword set that
# ships with every generated script (>= 10, deterministic per topic).
_KEYWORD_TEMPLATES = [
    "{topic} close up",
    "{topic} b-roll",
    "{topic} slow motion",
    "{topic} 4k footage",
    "vertical {topic} background",
    "{topic} aesthetic",
    "{topic} macro shot",
    "{topic} cinematic",
    "{topic} in motion",
    "{topic} detail shot",
    "{topic} atmospheric",
    "{topic} timelapse",
]


class MockLLMProvider(BaseLLMProvider):
    name = "mock"

    def is_configured(self) -> bool:
        return True

    async def list_models(self) -> List[DiscoveredModel]:
        """The stub is always "installed" — no daemon to query."""
        return [
            DiscoveredModel(
                id="memeforge-stub",
                label="memeforge-stub (deterministic offline stub)",
            )
        ]

    async def generate_script(
        self, topic: str, tone: str = "casual-commenter", max_lines: int = 8,
        duration_target: int = 60,
    ) -> GeneratedScript:
        rng = random.Random(topic)
        w_min, w_max = word_target(duration_target)
        target_words = (w_min + w_max) // 2

        opener = f"{rng.choice(_OPENERS)} {topic}."
        lines = [opener]
        words = len(opener.split())

        # Fill the body until the word budget (or the line cap) is hit.
        body_pool = [t.format(topic=topic) for t in _BODY]
        rng.shuffle(body_pool)
        while len(lines) < max(2, max_lines - 1) and words < target_words:
            if not body_pool:
                body_pool = [t.format(topic=topic) for t in _BODY]
                rng.shuffle(body_pool)
            body = body_pool.pop()
            lines.append(body)
            words += len(body.split())

        closer = rng.choice(_CLOSERS)
        lines.append(closer)
        # Deterministic visual keyword set (>= 10): the topic's key words
        # formatted through stock-search-friendly templates, in seeded
        # order. Stock sites match on short concrete phrases, so long
        # topics are trimmed to their first three words.
        topic_words = " ".join(topic.lower().split()[:3])
        keywords = list(
            dict.fromkeys(
                t.format(topic=topic_words)
                for t in rng.sample(
                    _KEYWORD_TEMPLATES, len(_KEYWORD_TEMPLATES)
                )
            )
        )
        # Mark the final line as the punchline (used for SFX timing later).
        return GeneratedScript(
            title=f"the {topic} take",
            lines=lines[:max_lines],
            keywords=keywords,
        )
