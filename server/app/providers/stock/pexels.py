"""Pexels stock video connector.

Live search (API key required):
    GET https://api.pexels.com/videos/search?query={q}&orientation=portrait
Keys are free: https://www.pexels.com/api/ — set PEXELS_API_KEY.

Unkeyed mode falls back to a curated set of *verified* vertical clips
served straight from Pexels' public CDN, so the studio flow (and even
full renders) work before any key is configured.
"""

from typing import List, Optional, Sequence

import httpx

from app.core import settings
from app.providers.stock.base import BaseStockProvider, DemoClip, StockVideo

_API_URL = "https://api.pexels.com/videos/search"

# Curated vertical demo clips (URLs verified against Pexels' public CDN).
# Only used when PEXELS_API_KEY is not configured; thumbnails use the
# video's first frame when no static image exists (the studio renders a
# <video preload="metadata"> element in that case).
_DEMO_CLIPS: List[DemoClip] = [
    DemoClip(
        id="2499611",
        url="https://videos.pexels.com/video-files/2499611/2499611-hd_1080_1920_30fps.mp4",
        title="Demo background — vertical b-roll",
        duration_s=21.8,
        thumbnail_url="https://images.pexels.com/videos/2499611/free-video-2499611.jpg",
        tags=["city", "walk", "people", "street", "night", "background"],
    ),
    DemoClip(
        id="4434242",
        url="https://videos.pexels.com/video-files/4434242/4434242-hd_1080_1920_24fps.mp4",
        title="Demo background — vertical b-roll 2",
        duration_s=22.1,
        tags=["nature", "abstract", "background", "texture"],
    ),
    DemoClip(
        id="4625747",
        url="https://videos.pexels.com/video-files/4625747/4625747-hd_1080_1920_24fps.mp4",
        title="Demo background — short vertical loop",
        duration_s=6.5,
        tags=["abstract", "loop", "background", "short"],
    ),
]


def _pick_video_file(files: List[dict]) -> Optional[dict]:
    """Best download file: the largest portrait HD file (≤ 1920 tall).

    Pexels returns one entry per rendition; ``hd`` quality in portrait
    orientation is the sweet spot for a 1080x1920 background without
    pulling 4K files.
    """
    candidates = [
        f for f in files
        if isinstance(f, dict) and f.get("link")
        and isinstance(f.get("width"), int) and isinstance(f.get("height"), int)
        and f.get("height", 0) >= f.get("width", 0)  # portrait only
        and f.get("height", 0) <= 1920
    ]
    if not candidates:
        # No portrait rendition: take the largest file as a fallback.
        sized = [f for f in files if isinstance(f, dict) and f.get("link")]
        return max(sized, key=lambda f: f.get("height") or 0, default=None)
    return max(candidates, key=lambda f: (f.get("quality") == "hd", f["height"]))


class PexelsProvider(BaseStockProvider):
    name = "pexels"

    def __init__(self, api_key: str = "", demo_clips: Sequence[DemoClip] = _DEMO_CLIPS) -> None:
        super().__init__(api_key=api_key or settings.PEXELS_API_KEY, demo_clips=demo_clips)

    async def search(self, query: str, per_page: int = 10) -> List[StockVideo]:
        if not self.is_configured():
            return self.demo_clips_for(query)
        params = {
            "query": query,
            "orientation": "portrait",
            "per_page": max(1, min(per_page, 40)),
            "size": "medium",
        }
        async with httpx.AsyncClient(timeout=settings.STOCK_SEARCH_TIMEOUT_S) as client:
            resp = await client.get(_API_URL, params=params, headers={"Authorization": self.api_key})
            resp.raise_for_status()
            data = resp.json()

        out: List[StockVideo] = []
        for item in data.get("videos", []):
            files = item.get("video_files") or []
            best = _pick_video_file(files)
            if best is None:
                continue
            user = item.get("user") or {}
            out.append(
                StockVideo(
                    id=str(item.get("id", "")),
                    provider=self.name,
                    title=str(user.get("name") or "Pexels clip"),
                    duration_s=float(item.get("duration") or 0.0),
                    width=int(best.get("width") or 0),
                    height=int(best.get("height") or 0),
                    thumbnail_url=str(item.get("image") or ""),
                    video_url=str(best["link"]),
                    author=str(user.get("name") or ""),
                )
            )
        return out
