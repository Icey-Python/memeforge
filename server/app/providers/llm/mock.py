"""Mock LLM provider.

Deterministic, offline script generator used for local development and
tests so the pipeline works end-to-end without any model or API key.
"""

import random

from app.providers.llm.base import BaseLLMProvider, GeneratedScript

_OPENERS = [
    "Nobody asked, but here's the truth about",
    "POV: you just discovered",
    "The council has decided:",
    "Gamer fact nobody wanted:",
    "Unpopular opinion inbound:",
]

_CLOSERS = [
    "And that's why we can't have nice things.",
    "Skill issue. Undeniable. Unforgivable.",
    "Touch grass. Immediately.",
    "This message was brought to you by sleep deprivation.",
    "Anyway, back to the grind.",
]


class MockLLMProvider(BaseLLMProvider):
    name = "mock"

    def is_configured(self) -> bool:
        return True

    async def generate_script(
        self, topic: str, tone: str = "reddit-commenter", max_lines: int = 8
    ) -> GeneratedScript:
        rng = random.Random(topic)
        body = [
            f"First off, {topic} is not a phase, it's a lifestyle.",
            f"My whole personality is basically {topic} at this point.",
            f"I told my squad about {topic} and now none of them talk to me.",
            f"They said {topic} builds character. They lied.",
            f"Every day I wake up and choose {topic} violence.",
            f"Nobody: ... Me: anyway, {topic}.",
            f"Sleep is temporary, {topic} is forever.",
            f"The tutorial never prepared me for {topic}.",
        ]
        lines = [
            f"{rng.choice(_OPENERS)} {topic}.",
            *body[: max(0, max_lines - 2)],
            rng.choice(_CLOSERS),
        ]
        # Mark the final line as the punchline (used for SFX timing later).
        return GeneratedScript(
            title=f"r/gaming on {topic}",
            lines=lines[:max_lines],
        )
