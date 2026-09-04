"""Stock video endpoints: Pexels / Pixabay search + AI keyword extraction.

Backs the studio "Video Background" node:
- GET  /stock/search          — vertical clips across providers
  (live APIs when keyed, curated demo clips otherwise)
- POST /stock/extract-keywords — 3-5 visual search queries from a
  script (LLM when configured, deterministic heuristic fallback)
- POST /stock/auto-select     — a planned fast-switching montage clip
  sequence from the script's keyword set, timed to its duration
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.providers.llm import registry as llm_registry
from app.providers.stock import registry as stock_registry
from app.providers.stock.keywords import extract_visual_keywords
from app.schemas.render_schema import (
    KeywordExtractRequest,
    KeywordExtractResponse,
    StockAutoSelectRequest,
    StockAutoSelectResponse,
    StockProviderInfo,
    StockSearchResponse,
    StockVideoResult,
)
from app.services import stock_select

logger = logging.getLogger("memeforge.stock")

stock_router = APIRouter()


@stock_router.get("/stock/search", response_model=StockSearchResponse)
async def search_stock_videos(
    q: str = Query(..., min_length=2, max_length=100),
    per_page: int = Query(default=10, ge=1, le=20),
    pexels_api_key: Optional[str] = Query(
        default=None, description="Pexels API key override (studio key vault)"
    ),
    pixabay_api_key: Optional[str] = Query(
        default=None, description="Pixabay API key override (studio key vault)"
    ),
    x_pexels_key: Optional[str] = Header(default=None, alias="X-Pexels-Key"),
    x_pixabay_key: Optional[str] = Header(default=None, alias="X-Pixabay-Key"),
):
    """Search vertical stock clips across Pexels and Pixabay.

    Client-supplied keys (headers or query params, from the studio's
    encrypted key vault) take priority over the server .env — providers
    without any key answer with a small set of curated demo clips
    (``is_demo``) so the flow works before keys are set; the response
    `notice` tells the studio to surface that.
    """
    pexels_key = x_pexels_key or pexels_api_key or None
    pixabay_key = x_pixabay_key or pixabay_api_key or None
    providers = stock_registry.get_stock_providers(
        pexels_api_key=pexels_key, pixabay_api_key=pixabay_key
    )
    videos = []
    unkeyed = []
    for provider in providers:
        if provider.is_configured():
            try:
                videos.extend(await provider.search(q, per_page=per_page))
            except Exception as exc:  # noqa: BLE001 - degrade to demos
                logger.warning("stock search %s failed: %s", provider.name, exc)
                videos.extend(provider.demo_clips_for(q))
        else:
            unkeyed.append(provider.name)
            videos.extend(provider.demo_clips_for(q))

    if not videos:
        raise HTTPException(
            status_code=502,
            detail="Stock search returned no clips (no providers available).",
        )

    notice = None
    if unkeyed:
        env_names = " and ".join(f"{n.upper()}_API_KEY" for n in unkeyed)
        notice = (
            f"Showing curated demo clips — add {env_names} in server/.env "
            "or the studio key vault (Settings → API Keys) for live results."
        )
    elif any(v.is_demo for v in videos):
        notice = "Some providers fell back to demo clips after an API error."

    return StockSearchResponse(
        query=q,
        videos=videos,
        providers=[
            StockProviderInfo(**p)
            for p in stock_registry.list_stock_providers(
                pexels_api_key=pexels_key, pixabay_api_key=pixabay_key
            )
        ],
        notice=notice,
    )


@stock_router.post("/stock/extract-keywords", response_model=KeywordExtractResponse)
async def extract_stock_keywords(request: KeywordExtractRequest):
    """Turn a script into 3-5 visual stock-video search queries.

    Uses the configured LLM connector when one answers; otherwise a
    deterministic offline heuristic (stopword-stripped frequency
    analysis) keeps the button working with zero setup.
    """
    provider = llm_registry.get_llm_provider(
        request.provider.value,
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
    )
    queries, source = await extract_visual_keywords(request.script, provider)
    if not queries:
        raise HTTPException(
            status_code=422,
            detail="Could not derive search queries from an empty script.",
        )
    return KeywordExtractResponse(queries=queries, source=source)


@stock_router.post(
    "/stock/auto-select", response_model=StockAutoSelectResponse
)
async def auto_select_stock_montage(
    request: StockAutoSelectRequest,
    x_pexels_key: Optional[str] = Header(default=None, alias="X-Pexels-Key"),
    x_pixabay_key: Optional[str] = Header(default=None, alias="X-Pixabay-Key"),
):
    """Auto-build a fast-switching montage from the script's keywords.

    Queries Pexels / Pixabay round-robin over the keyword set (the one
    that ships with /generate-script; a bare script falls back to the
    offline heuristic) and returns an ordered clip sequence sized for
    the script duration — each clip plays a ~1.5-3s cut in the render
    (see RenderRequest.stock_montage). A fresh `seed` reshuffles the
    picks; `exclude` powers the per-clip swap flow.
    """
    keywords = stock_select.resolve_keywords(request.keywords, request.script)
    if not keywords:
        raise HTTPException(
            status_code=422,
            detail=(
                "No keywords to search with — pass the script keyword set "
                "or script lines to derive one."
            ),
        )

    # Client-supplied keys (headers or body, from the studio's encrypted
    # key vault) take priority over the server .env — same contract as
    # GET /stock/search.
    pexels_key = x_pexels_key or request.pexels_api_key or None
    pixabay_key = x_pixabay_key or request.pixabay_api_key or None
    providers = stock_registry.get_stock_providers(
        pexels_api_key=pexels_key, pixabay_api_key=pixabay_key
    )

    duration_s = (
        request.duration_s
        if request.duration_s is not None
        else stock_select.estimate_duration_s(request.script)
    )
    exclude = [(c.provider, c.id) for c in request.exclude]
    clips = await stock_select.auto_select_clips(
        providers,
        keywords,
        duration_s=duration_s,
        segment_s=request.segment_s,
        seed=request.seed,
        exclude=exclude,
    )
    if not clips:
        raise HTTPException(
            status_code=502,
            detail=(
                "Stock search returned no montage clips (no providers "
                "answered with usable vertical footage)."
            ),
        )

    notice = None
    unkeyed = [p.name for p in providers if not p.is_configured()]
    if unkeyed:
        env_names = " and ".join(f"{n.upper()}_API_KEY" for n in unkeyed)
        notice = (
            f"Showing curated demo clips — add {env_names} in server/.env "
            "or the studio key vault (Settings → API Keys) for live results."
        )

    return StockAutoSelectResponse(
        clips=clips,
        keywords=keywords,
        duration_s=duration_s,
        segment_s=request.segment_s,
        segments_needed=stock_select.segments_needed(
            duration_s, request.segment_s
        ),
        notice=notice,
        providers=[
            StockProviderInfo(**p)
            for p in stock_registry.list_stock_providers(
                pexels_api_key=pexels_key, pixabay_api_key=pixabay_key
            )
        ],
    )
