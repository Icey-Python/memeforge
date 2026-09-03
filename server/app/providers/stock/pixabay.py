"""Pixabay stock video connector.

Live search (API key required):
    GET https://pixabay.com/api/videos/?key={key}&q={q}&video_type=film
Keys are free: https://pixabay.com/api/docs/ — set PIXABAY_API_KEY.

Pixabay's CDN blocks unauthenticated direct downloads, so the unkeyed
fallback returns no clips (the Pexels demo set covers demo mode); live
searches return the provider's ``large`` rendition with a Vimeo-hosted
thumbnail.
"""

from typing import List, Sequence

import httpx

from app.core import settings
from app.providers.stock.base import BaseStockProvider, DemoClip, StockVideo

_API_URL = "https://pixabay.com/api/videos/"

# Pixabay video thumbnails are served from their Vimeo CDN with this
# pattern (picture_id comes on every video hit).
_THUMB_PATTERN = "https://i.vimeocdn.com/video/{picture_id}_640x360.jpg"


def _pick_rendition(videos: dict) -> dict:
    """Best rendition dict: large > medium > small > tiny."""
    for key in ("large", "medium", "small", "tiny"):
        rend = videos.get(key)
        if rend and rend.get("url"):
            return rend
    return {}


class PixabayProvider(BaseStockProvider):
    name = "pixabay"

    def __init__(self, api_key: str = "", demo_clips: Sequence[DemoClip] = ()) -> None:
        super().__init__(api_key=api_key or settings.PIXABAY_API_KEY, demo_clips=demo_clips)

    async def search(self, query: str, per_page: int = 10) -> List[StockVideo]:
        if not self.is_configured():
            return self.demo_clips_for(query)
        params = {
            "key": self.api_key,
            "q": query,
            "video_type": "film",
            "safesearch": "true",
            "per_page": max(3, min(per_page * 3, 60)),  # overfetch: portrait filter below
        }
        async with httpx.AsyncClient(timeout=settings.STOCK_SEARCH_TIMEOUT_S) as client:
            resp = await client.get(_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        out: List[StockVideo] = []
        for hit in data.get("hits", []):
            rendition = _pick_rendition(hit.get("videos") or {})
            if not rendition:
                continue
            width = int(rendition.get("width") or 0)
            height = int(rendition.get("height") or 0)
            # Portrait-only results (the render is 9:16); landscape pixabay
            # films letterbox badly, so they are filtered out client-side.
            if height and width and height < width:
                continue
            tags = str(hit.get("tags") or "").split(", ")
            out.append(
                StockVideo(
                    id=str(hit.get("id", "")),
                    provider=self.name,
                    title=tags[0].strip().title() if tags and tags[0] else "Pixabay clip",
                    duration_s=float(hit.get("duration") or 0.0),
                    width=width,
                    height=height,
                    thumbnail_url=_THUMB_PATTERN.format(
                        picture_id=hit.get("picture_id", "")
                    ),
                    video_url=str(rendition["url"]),
                    author=str(hit.get("user") or ""),
                )
            )
            if len(out) >= per_page:
                break
        return out
