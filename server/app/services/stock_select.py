"""Auto-select a fast-switching stock montage from script keywords.

The studio's stock tab can build the whole background in one click:
the keyword set that ships with a generated script (10+ visual search
phrases) drives round-robin Pexels/Pixabay searches, producing an
ordered clip sequence timed to the script duration — each clip plays a
1.5-3s cut before the montage moves on (see stitcher.plan_montage_segments).

Selection strategy:
- keywords are consumed in order (they follow the script's timeline),
  so clip N roughly matches script point N;
- every keyword is searched across all configured providers (live keys
  first; unkeyed providers answer with curated demo clips);
- a seeded shuffle refreshes the picks without waiting for provider
  ranking drift, powering the studio's shuffle / per-clip swap buttons.
"""

import math
import random
from typing import List, Optional, Sequence, Set, Tuple

from app.core import settings
from app.providers.stock.base import BaseStockProvider
from app.providers.stock.keywords import heuristic_keywords
from app.schemas.render_schema import StockClipRef, StockVideoResult

# Fallback spoken pace (words/sec) when no duration is supplied —
# mirrors the frontend's estimateSpokenSeconds.
_WORDS_PER_SEC = 2.4
# Candidates fetched per keyword search (variety for shuffle/refresh).
_PER_PAGE = 6
# Hard floor on clip length: shorter sources cannot fill a 1.5s cut.
_MIN_CLIP_S = 2.0
# Upper bound on the keyword list we will search (rate-limit hygiene).
_MAX_KEYWORDS = 14


def estimate_duration_s(script: Sequence[str]) -> float:
    """Spoken-length estimate for a script (~2.4 words/sec of speech)."""
    words = sum(len(line.split()) for line in script if line.strip())
    return max(10.0, words / _WORDS_PER_SEC)


def resolve_keywords(
    keywords: Sequence[str], script: Sequence[str]
) -> List[str]:
    """The keyword set to search: explicit keywords win; a script alone
    falls back to the offline heuristic extractor."""
    cleaned = [k.strip().lower() for k in keywords if k.strip()]
    if cleaned:
        return list(dict.fromkeys(cleaned))[:_MAX_KEYWORDS]
    text = "\n".join(script)
    if not text.strip():
        return []
    return heuristic_keywords(
        text, max_queries=_MAX_KEYWORDS, min_queries=6
    )[:_MAX_KEYWORDS]


def segments_needed(duration_s: float, segment_s: float) -> int:
    """How many ~segment_s cuts cover the duration."""
    return max(1, math.ceil(duration_s / max(segment_s, 0.1)))


async def _search_pool(
    providers: Sequence[BaseStockProvider], keyword: str
) -> List[StockVideoResult]:
    """One keyword searched across every provider (failures skipped)."""
    pool: List[StockVideoResult] = []
    for provider in providers:
        try:
            pool.extend(await provider.search(keyword, per_page=_PER_PAGE))
        except Exception:  # noqa: BLE001 - provider hiccup: skip it
            continue
    return pool


async def auto_select_clips(
    providers: Sequence[BaseStockProvider],
    keywords: Sequence[str],
    duration_s: float,
    segment_s: float,
    seed: Optional[int] = None,
    exclude: Sequence[Tuple[str, str]] = (),
) -> List[StockClipRef]:
    """Ordered clip sequence for a fast-switching montage.

    Round-robins the keywords (in order, so the sequence follows the
    script timeline), taking one new clip per keyword per pass across
    every provider, until `min(segments_needed, STOCK_MAX_MONTAGE_CLIPS)`
    unique clips are picked or the candidates run dry. `seed` shuffles
    each keyword's candidate pool (refresh/shuffle); `exclude` skips
    (provider, id) pairs (the per-clip swap flow).
    """
    if not keywords:
        return []
    target = min(
        segments_needed(duration_s, segment_s),
        settings.STOCK_MAX_MONTAGE_CLIPS,
    )
    rng = random.Random(seed) if seed is not None else None
    skip: Set[Tuple[str, str]] = set(exclude)

    # Search every keyword once up front (live keys first; unkeyed
    # providers answer with demo clips). A seeded shuffle keeps
    # refreshes fresh without waiting for provider ranking drift.
    pools: List[List[StockVideoResult]] = []
    for keyword in keywords:
        pool = await _search_pool(providers, keyword)
        if rng is not None:
            rng.shuffle(pool)
        pools.append(pool)

    picked: List[StockClipRef] = []
    picked_keys: Set[Tuple[str, str]] = set()
    cursor = [0] * len(pools)  # next-unexamined candidate per keyword

    # Multi-pass round-robin: pass 1 takes the best clip for every
    # keyword in script order; later passes pull alternates from the
    # same pools until the montage has enough variety.
    while len(picked) < target:
        added = False
        for i, keyword in enumerate(keywords):
            if len(picked) >= target:
                break
            while cursor[i] < len(pools[i]):
                video = pools[i][cursor[i]]
                cursor[i] += 1
                if video.duration_s < _MIN_CLIP_S:
                    continue
                key = (video.provider, video.id)
                if key in picked_keys or key in skip:
                    continue
                picked_keys.add(key)
                picked.append(
                    StockClipRef(
                        provider=video.provider,
                        id=video.id,
                        url=video.video_url,
                        duration_s=video.duration_s,
                        label=video.title or keyword,
                        keyword=keyword,
                    )
                )
                added = True
                break
        if not added:
            break  # every keyword exhausted its candidates
    return picked
