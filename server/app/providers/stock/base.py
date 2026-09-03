"""Stock video provider base: shared model + demo-clip fallback.

A stock provider turns a text query into a list of vertical HD clips
(id, direct download URL, duration, thumbnail). The renderer downloads
the picked clips and stitches them into one continuous background
(see services/rendering/stitcher.py).

Demo fallback: without an API key every provider still answers with a
small curated set of verified vertical clips (marked ``is_demo``) so the
studio wizard can be exercised — and renders actually work — before any
keys are configured.
"""

import re
from typing import List, Sequence

from pydantic import BaseModel

from app.schemas.render_schema import StockVideoResult


# One shared model for provider results and API responses.
StockVideo = StockVideoResult


class DemoClip(BaseModel):
    """Curated fallback clip entry (verified public CDN URL)."""

    id: str
    url: str
    title: str
    duration_s: float
    width: int = 1080
    height: int = 1920
    thumbnail_url: str = ""
    tags: List[str] = []


def _demo_matches(clip: DemoClip, query: str) -> bool:
    """Loose demo search: any query word hits a clip tag/title word."""
    qwords = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
    text = " ".join(clip.tags) + " " + clip.title.lower()
    text_words = set(re.findall(r"[a-z]+", text))
    return bool(qwords & text_words)


class BaseStockProvider:
    """Contract for stock video connectors (Pexels, Pixabay, ...)."""

    name: str = "base"

    def __init__(self, api_key: str = "", demo_clips: Sequence[DemoClip] = ()) -> None:
        self.api_key = api_key
        self._demo_clips = list(demo_clips)

    def is_configured(self) -> bool:
        """Whether the provider has an API key for live searches."""
        return bool(self.api_key)

    async def search(self, query: str, per_page: int = 10) -> List[StockVideo]:
        raise NotImplementedError

    def demo_clips_for(self, query: str) -> List[StockVideo]:
        """Curated fallback clips for unkeyed mode (tag-matched first)."""
        clips = list(self._demo_clips)
        if not clips:
            return []
        matched = [c for c in clips if _demo_matches(c, query)]
        picked = matched or clips
        return [
            StockVideo(
                id=f"{self.name}-demo-{c.id}",
                provider=self.name,
                title=c.title,
                duration_s=c.duration_s,
                width=c.width,
                height=c.height,
                thumbnail_url=c.thumbnail_url,
                video_url=c.url,
                author="Pexels (free stock)",
                is_demo=True,
            )
            for c in picked
        ]
