"""Stock video search + keyword extraction + multi-clip stitching tests.

Covers the studio "Video Background" step:
- unkeyed demo fallback + live Pexels / Pixabay payload normalization
- AI keyword extraction (LLM path + deterministic heuristic fallback)
- render validation for stock-clip backgrounds
- the clip budget planner and the ffmpeg stitch argv
- an end-to-end stitch integration test when ffmpeg is available
"""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import settings
from app.main import app
from app.schemas.render_schema import StockClipRef
from app.services.rendering import compositor, stitcher

client = TestClient(app)


# --- Fake httpx plumbing (mirrors the patterns in test_api.py) -------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")

    def json(self):
        return self.payload


class FakeSearchClient:
    """Async client fake for search endpoints (get with params/headers)."""

    def __init__(self, payload, expected_url=None, expected_path=""):
        self.payload = payload
        self.expected_url = expected_url
        self.expected_path = expected_path

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, headers=None):
        if self.expected_path:
            assert self.expected_path in url, url
        return FakeResponse(self.payload)


def _make_fake_client(module, payload, expected_path):
    def factory(**kwargs):
        return FakeSearchClient(payload, expected_path=expected_path)

    return factory


# --- Search: unkeyed demo fallback ------------------------------------------


def test_stock_search_unkeyed_returns_demo_clips(monkeypatch):
    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "")
    resp = client.get("/api/v1/stock/search", params={"q": "noodles"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["videos"]) > 0
    assert all(v["is_demo"] for v in body["videos"])
    assert all(v["provider"] == "pexels" for v in body["videos"])
    # Demo mode tells the studio to configure keys.
    assert "PEXELS_API_KEY" in body["notice"]
    providers = {p["id"]: p["keyed"] for p in body["providers"]}
    assert providers == {"pexels": False, "pixabay": False}


def test_stock_search_rejects_short_query():
    resp = client.get("/api/v1/stock/search", params={"q": "a"})
    assert resp.status_code == 422


# --- Search: live provider payload normalization ------------------------------


def test_stock_search_pexels_parses_live_payload(monkeypatch):
    from app.providers.stock import pexels as pexels_module

    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "")
    payload = {
        "videos": [
            {
                "id": 123,
                "duration": 9,
                "image": "https://images.pexels.com/videos/123/pic.jpg",
                "user": {"name": "Ada"},
                "video_files": [
                    # landscape rendition must be skipped
                    {"link": "https://cdn/x-land.mp4", "width": 1920, "height": 1080,
                     "quality": "hd"},
                    # portrait hd is the pick
                    {"link": "https://cdn/x-port.mp4", "width": 1080, "height": 1920,
                     "quality": "hd"},
                    {"link": "https://cdn/x-port-sd.mp4", "width": 540, "height": 960,
                     "quality": "sd"},
                ],
            }
        ]
    }
    monkeypatch.setattr(
        pexels_module.httpx, "AsyncClient",
        _make_fake_client(pexels_module, payload, "api.pexels.com/videos/search"),
    )
    monkeypatch.setattr(settings, "PEXELS_API_KEY", "test-key")

    resp = client.get("/api/v1/stock/search", params={"q": "noodles"})
    assert resp.status_code == 200
    body = resp.json()
    # Pixabay stays unkeyed in this test, but a live Pexels key wins:
    # no demo clips mixed in and no demo notice.
    assert len(body["videos"]) == 1
    v = body["videos"][0]
    assert v["id"] == "123"
    assert v["provider"] == "pexels"
    assert v["video_url"] == "https://cdn/x-port.mp4"
    assert v["duration_s"] == 9.0
    assert v["author"] == "Ada"
    assert v["thumbnail_url"].endswith("pic.jpg")
    assert body["notice"] is None


def test_stock_search_all_keyed_errors_demo_notice(monkeypatch):
    """Every keyed provider erroring degrades to demo clips + a notice."""
    from app.providers.stock import pexels as pexels_module
    from app.providers.stock import pixabay as pixabay_module

    monkeypatch.setattr(settings, "PEXELS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "test-key")

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params=None, headers=None):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(pexels_module.httpx, "AsyncClient", FailingClient)
    monkeypatch.setattr(pixabay_module.httpx, "AsyncClient", FailingClient)

    resp = client.get("/api/v1/stock/search", params={"q": "noodles"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["videos"]) > 0
    assert all(v["is_demo"] for v in body["videos"])
    assert "API error" in body["notice"]


def test_stock_search_pixabay_parses_live_payload(monkeypatch):
    from app.providers.stock import pixabay as pixabay_module

    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "test-key")
    payload = {
        "hits": [
            {
                "id": 456,
                "duration": 12,
                "picture_id": "pic456",
                "user": "Bob",
                "tags": "noodle, bowl, cooking",
                "videos": {
                    "large": {"url": "https://cdn.pixabay.com/vid_large.mp4",
                              "width": 1080, "height": 1920},
                    "medium": {"url": "https://cdn.pixabay.com/vid_med.mp4",
                               "width": 540, "height": 960},
                },
            },
            {
                # landscape hit is filtered out
                "id": 789,
                "duration": 8,
                "picture_id": "pic789",
                "user": "Eve",
                "tags": "city, street",
                "videos": {
                    "large": {"url": "https://cdn.pixabay.com/land.mp4",
                              "width": 1920, "height": 1080},
                },
            },
        ]
    }
    monkeypatch.setattr(
        pixabay_module.httpx, "AsyncClient",
        _make_fake_client(pixabay_module, payload, "pixabay.com/api/videos"),
    )

    resp = client.get("/api/v1/stock/search", params={"q": "noodles"})
    assert resp.status_code == 200
    videos = [v for v in resp.json()["videos"] if not v["is_demo"]]
    assert len(videos) == 1
    v = videos[0]
    assert v["id"] == "456"
    assert v["provider"] == "pixabay"
    assert v["video_url"] == "https://cdn.pixabay.com/vid_large.mp4"
    assert v["title"] == "Noodle"
    assert "pic456" in v["thumbnail_url"]


# --- Keyword extraction -------------------------------------------------------


def test_extract_keywords_heuristic_offline():
    resp = client.post(
        "/api/v1/stock/extract-keywords",
        json={
            "script": (
                "Noodles noodles noodles. First you boil the noodles. "
                "Then the chef adds the noodle broth. Asian street food "
                "noodle bowls everywhere."
            ),
            "provider": "mock",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 3 <= len(body["queries"]) <= 5
    assert body["source"] == "heuristic"
    assert any("noodle" in q for q in body["queries"])


def test_extract_keywords_llm_path(monkeypatch):
    from app.providers.llm import openai_compatible as openai_module

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"queries": ["boiling noodles", '
                            '"chef cooking pasta", "asian street food noodle bowl"]}'
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            assert url.endswith("/chat/completions")
            return FakeResp()

    monkeypatch.setattr(openai_module.httpx, "AsyncClient", FakeClient)

    resp = client.post(
        "/api/v1/stock/extract-keywords",
        json={
            "script": "how noodles are made in a factory",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "k",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "llm"
    assert body["queries"] == [
        "boiling noodles",
        "chef cooking pasta",
        "asian street food noodle bowl",
    ]


def test_extract_keywords_llm_failure_falls_back_offline(monkeypatch):
    from app.providers.llm import openai_compatible as openai_module

    class BoomClient:
        def __init__(self, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            raise RuntimeError("endpoint down")

    monkeypatch.setattr(openai_module.httpx, "AsyncClient", BoomClient)

    resp = client.post(
        "/api/v1/stock/extract-keywords",
        json={
            "script": "how noodles are made in a factory",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "heuristic"
    assert len(body["queries"]) >= 3


def test_extract_keywords_rejects_empty_script():
    resp = client.post(
        "/api/v1/stock/extract-keywords", json={"script": ""}
    )
    assert resp.status_code == 422


def test_heuristic_keywords_deterministic_shape():
    from app.providers.stock.keywords import heuristic_keywords

    queries = heuristic_keywords(
        "Noodles noodles. Boiling broth. Street food street food."
    )
    assert 3 <= len(queries) <= 5
    assert all(isinstance(q, str) and q for q in queries)
    # Frequent bigrams surface as queries.
    assert "street food" in queries


# --- Render validation ---------------------------------------------------------


def test_render_requires_background_source():
    resp = client.post(
        "/api/v1/render", json={"script": ["hello", "world"]}
    )
    assert resp.status_code == 400
    assert "No background source" in resp.json()["detail"]


def test_render_rejects_too_many_stock_clips(monkeypatch):
    monkeypatch.setattr(settings, "STOCK_MAX_CLIPS", 3)
    clips = [
        {
            "provider": "pexels",
            "id": str(i),
            "url": f"https://cdn/{i}.mp4",
            "duration_s": 5.0,
        }
        for i in range(4)
    ]
    resp = client.post(
        "/api/v1/render", json={"script": ["hello"], "stock_clips": clips}
    )
    assert resp.status_code == 400
    assert "Too many stock clips" in resp.json()["detail"]


def test_render_rejects_unknown_stock_provider():
    resp = client.post(
        "/api/v1/render",
        json={
            "script": ["hello"],
            "stock_clips": [
                {
                    "provider": "vimeo",
                    "id": "1",
                    "url": "https://cdn/1.mp4",
                    "duration_s": 5.0,
                }
            ],
        },
    )
    assert resp.status_code == 400
    assert "Unknown stock provider" in resp.json()["detail"]


def test_render_accepts_stock_clips(monkeypatch):
    from app.services.rendering import renderer as renderer_module

    async def noop(job_id, request):
        return None

    monkeypatch.setattr(renderer_module, "run_render_job", noop)
    resp = client.post(
        "/api/v1/render",
        json={
            "script": ["hello", "world"],
            "stock_clips": [
                {
                    "provider": "pexels",
                    "id": "1",
                    "url": "https://cdn/1.mp4",
                    "duration_s": 6.0,
                    "label": "noodle closeup",
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"]
    assert body["status"] == "queued"


# --- Stitching: budget planner + argv ------------------------------------------


def test_plan_clip_budgets_trims_overflow():
    # 10 + 10 + 10 vs target 15 → [10, 5], third clip dropped.
    assert stitcher.plan_clip_budgets([10, 10, 10], 15.0) == [10.0, 5.0]


def test_plan_clip_budgets_repeats_when_short():
    # 5 + 5 vs target 17 → repeats the sequence, trimming the last cycle.
    budgets = stitcher.plan_clip_budgets([5, 5], 17.0)
    assert sum(budgets) == pytest.approx(17.0)
    assert len(budgets) == 4  # 5, 5, 5, 2


def test_plan_clip_budgets_rejects_bad_input():
    with pytest.raises(ValueError):
        stitcher.plan_clip_budgets([], 10.0)
    with pytest.raises(ValueError):
        stitcher.plan_clip_budgets([5.0], 0.0)


def test_stitch_background_args_shape(tmp_path):
    clips = [(tmp_path / "a.mp4", 8.0), (tmp_path / "b.mp4", 6.0)]
    args = stitcher.stitch_background_args(clips, tmp_path / "out.mp4", 11.0)
    joined = " ".join(args)
    assert "concat=n=2:v=1:a=0" in joined
    # Ordered-playlist mode: whole clips from 0:00, trimmed to budget.
    assert "trim=start=0.000:duration=8.000" in joined
    assert "trim=start=0.000:duration=3.000" in joined
    # Normalized to the render canvas, audio dropped.
    assert "scale=1080:1920" in joined
    assert "-an" in args
    assert str(tmp_path / "out.mp4") in args


def test_stitch_background_args_single_clip(tmp_path):
    clips = [(tmp_path / "a.mp4", 9.0)]
    args = stitcher.stitch_background_args(clips, tmp_path / "out.mp4", 4.0)
    joined = " ".join(args)
    assert "concat=n=" not in joined
    assert "trim=start=0.000:duration=4.000" in joined


def test_stitch_background_args_montage_segments(tmp_path):
    """Montage plans drive per-segment in-points, not whole clips."""
    clips = [(tmp_path / "a.mp4", 12.0), (tmp_path / "b.mp4", 9.0)]
    segments = [
        stitcher.StitchSegment(0, 0.0, 2.5),
        stitcher.StitchSegment(1, 0.0, 3.0),
        stitcher.StitchSegment(0, 2.5, 1.5),  # clip A continues at 2.5s
    ]
    args = stitcher.stitch_background_args(
        clips, tmp_path / "out.mp4", 7.0, segments=segments
    )
    joined = " ".join(args)
    assert "concat=n=3:v=1:a=0" in joined
    assert "trim=start=0.000:duration=2.500" in joined
    assert "trim=start=0.000:duration=3.000" in joined
    assert "trim=start=2.500:duration=1.500" in joined
    # The same source file is opened once per segment (fresh in-point).
    assert joined.count(f"-i {tmp_path / 'a.mp4'}") == 2
    assert joined.count(f"-i {tmp_path / 'b.mp4'}") == 1


# --- Download (MockTransport) ---------------------------------------------------


def test_download_stock_clips_streams_to_disk(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/good.mp4":
            return httpx.Response(200, content=b"VIDEOFBYTES" * 50)
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(stitcher.httpx, "AsyncClient", factory)

    refs = [
        StockClipRef(provider="pexels", id="1", url="https://cdn/good.mp4",
                     duration_s=5.0, label="clip 1"),
        StockClipRef(provider="pexels", id="2", url="https://cdn/good.mp4",
                     duration_s=4.0, label="clip 2"),
    ]
    import asyncio

    out = asyncio.run(stitcher.download_stock_clips(refs, Path("/tmp")))
    assert len(out) == 2
    for path, duration in out:
        assert path.exists()
        assert path.stat().st_size > 0
        assert duration in (5.0, 4.0)


def test_download_stock_clips_raises_on_404(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(stitcher.httpx, "AsyncClient", factory)

    refs = [
        StockClipRef(provider="pexels", id="1", url="https://cdn/gone.mp4",
                     duration_s=5.0),
    ]
    import asyncio

    with pytest.raises(RuntimeError, match="download failed"):
        asyncio.run(stitcher.download_stock_clips(refs, Path("/tmp")))


# --- End-to-end stitch (real ffmpeg) ---------------------------------------------

ffmpeg_missing = not compositor.ffmpeg_available()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not on PATH")
def test_stitch_background_end_to_end(tmp_path):
    """Three synthetic clips stitch into one 1080x1920 cut sequence."""
    import asyncio

    clips = []
    for i in range(3):
        src = tmp_path / f"src-{i}.mp4"
        asyncio.run(compositor.run_ffmpeg([
            settings.FFMPEG_BIN, "-y",
            "-f", "lavfi", "-t", "2.0",
            "-i", f"testsrc2=size=540x960:rate=30",
            "-vf", "scale=1080:1920",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(src),
        ]))
        clips.append((src, 2.0))

    out = asyncio.run(
        stitcher.stitch_background(clips, tmp_path / "bg.mp4", 5.5)
    )
    assert out.exists()
    duration = asyncio.run(compositor.probe_video_duration(out))
    assert duration == pytest.approx(5.5, abs=0.35)


# --- Fast-switching montage planner -----------------------------------------------


def test_plan_montage_segments_covers_target_with_rhythm():
    """Many clips: every cut lands in 1.5-3s and the sum is exact."""
    segments = stitcher.plan_montage_segments([12.0] * 30, 60.3)
    assert abs(sum(s.duration_s for s in segments) - 60.3) < 0.05
    # Rhythm cycles max → mid → min so cuts don't land on a metronome.
    durations = [round(s.duration_s, 3) for s in segments[:3]]
    assert durations == [3.0, 2.25, 1.5]
    assert all(1.0 <= s.duration_s <= 3.0 + 1e-9 for s in segments[:-1])
    # First pass walks the clips in order (clip N matches script point N).
    assert [s.clip_index for s in segments[:5]] == [0, 1, 2, 3, 4]
    assert all(s.start_s == 0.0 for s in segments[:5])


def test_plan_montage_segments_cycles_with_fresh_inpoints():
    """Few clips: later passes CONTINUE each clip where it stopped
    (never replaying the same first seconds), skipping tail slivers."""
    segments = stitcher.plan_montage_segments([5.0, 4.0], 20.0)
    assert abs(sum(s.duration_s for s in segments) - 20.0) < 0.05
    # No mid-sequence blips: every non-final cut is a proper 1.5s+ cut.
    assert all(1.5 - 1e-6 <= s.duration_s <= 3.0 + 1e-6
               for s in segments[:-1])
    # clip0's segments advance: 0 → 3.0 → (wrap) 0 → 2.25 …
    clip0_starts = [s.start_s for s in segments if s.clip_index == 0]
    assert clip0_starts[0] == 0.0
    assert clip0_starts[1] == pytest.approx(3.0)


def test_plan_montage_segments_short_clips_play_whole():
    """A clip shorter than the min segment still contributes (whole)."""
    segments = stitcher.plan_montage_segments([1.2, 10.0], 12.0)
    assert abs(sum(s.duration_s for s in segments) - 12.0) < 0.05
    short_takes = [s for s in segments if s.clip_index == 0]
    assert short_takes
    assert all(s.duration_s == pytest.approx(1.2) for s in short_takes)


def test_plan_montage_segments_single_clip_cuts():
    """One long clip becomes a sequence of short cuts, not one long play."""
    segments = stitcher.plan_montage_segments([30.0], 8.0)
    assert len(segments) >= 3
    assert abs(sum(s.duration_s for s in segments) - 8.0) < 0.05
    starts = [s.start_s for s in segments]
    assert starts == sorted(starts)  # advancing in-point, no replay


def test_plan_montage_segments_caps_graph_size():
    """Beyond the segment cap the plan stops (the compositor's
    -stream_loop covers the remainder)."""
    segments = stitcher.plan_montage_segments([10.0, 10.0], 600.0)
    assert len(segments) == stitcher._MAX_MONTAGE_SEGMENTS


def test_plan_montage_segments_rejects_bad_input():
    with pytest.raises(ValueError):
        stitcher.plan_montage_segments([], 10.0)
    with pytest.raises(ValueError):
        stitcher.plan_montage_segments([5.0], 0.0)


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not on PATH")
def test_stitch_montage_end_to_end(tmp_path):
    """A montage plan renders as one exact-duration 1080x1920 sequence."""
    import asyncio

    clips = []
    for i in range(3):
        src = tmp_path / f"src-{i}.mp4"
        asyncio.run(compositor.run_ffmpeg([
            settings.FFMPEG_BIN, "-y",
            "-f", "lavfi", "-t", "4.0",
            "-i", f"testsrc2=size=540x960:rate=30",
            "-vf", "scale=1080:1920",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(src),
        ]))
        clips.append((src, 4.0))

    segments = stitcher.plan_montage_segments([4.0] * 3, 7.5)
    assert len(segments) >= 3  # fast cuts, not full clips
    out = asyncio.run(
        stitcher.stitch_background(
            clips, tmp_path / "bg.mp4", 7.5, segments=segments
        )
    )
    assert out.exists()
    duration = asyncio.run(compositor.probe_video_duration(out))
    assert duration == pytest.approx(7.5, abs=0.35)


# --- Montage auto-selection --------------------------------------------------------


class FakeMontageProvider:
    """Deterministic stand-in stock provider: returns keyword-tagged clips."""

    def __init__(self, clips_by_query: dict, fail: bool = False):
        self.clips_by_query = clips_by_query
        self.fail = fail
        self.queries: list = []

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, per_page: int = 10):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("provider down")
        return self.clips_by_query.get(query, [])[:per_page]


def _clip(provider: str, kid: str, keyword: str, duration_s: float = 8.0):
    from app.schemas.render_schema import StockVideoResult

    return StockVideoResult(
        id=str(kid),
        provider=provider,
        title=f"{keyword} #{kid}",
        duration_s=duration_s,
        width=1080,
        height=1920,
        thumbnail_url="",
        video_url=f"https://cdn/{provider}/{kid}.mp4",
        author="tester",
    )


def _patch_providers(monkeypatch, *providers):
    from app.providers.stock import registry as stock_registry

    monkeypatch.setattr(
        stock_registry,
        "get_stock_providers",
        lambda *args, **kwargs: list(providers),
    )


def test_auto_select_builds_keyword_timed_sequence(monkeypatch):
    """60s @ 2.25s cuts → 27 segments; picks walk the keywords in order."""
    keywords = [f"kw{i}" for i in range(12)]
    provider = FakeMontageProvider(
        {
            kw: [_clip("pexels", f"{kw}-{i}", kw) for i in range(4)]
            for kw in keywords
        }
    )
    _patch_providers(monkeypatch, provider)

    resp = client.post(
        "/api/v1/stock/auto-select",
        json={
            "keywords": keywords,
            "duration_s": 60.0,
            "segment_s": 2.25,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # 60 / 2.25 = 26.67 → 27 segments; enough candidates → 27 unique clips.
    assert body["segments_needed"] == 27
    assert len(body["clips"]) == 27
    # Round-robin: the first pass takes one clip per keyword in order.
    assert [c["keyword"] for c in body["clips"][:12]] == keywords
    # Every keyword got searched.
    assert set(provider.queries) == set(keywords)
    # Clip refs carry everything the render + swap flow need.
    first = body["clips"][0]
    assert first["provider"] == "pexels"
    assert first["url"] == "https://cdn/pexels/kw0-0.mp4"
    assert first["keyword"] == "kw0"
    assert first["duration_s"] == 8.0


def test_auto_select_derives_keywords_and_duration_from_script(monkeypatch):
    """No keywords: the heuristic extracts them; duration follows the
    script's word count (~2.4 words/sec)."""
    provider = FakeMontageProvider(
        {
            kw: [_clip("pexels", kw, kw)]
            for kw in (
                "pizza", "pizza close up", "pizza slow motion", "pizza 4k",
                "pizza cinematic", "pizza b-roll", "pizza background",
                "dough", "oven", "night",
            )
        }
    )
    _patch_providers(monkeypatch, provider)

    script = ["pizza pizza pizza dough"] * 15  # 60 words
    resp = client.post(
        "/api/v1/stock/auto-select",
        json={"script": script, "segment_s": 2.25},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["keywords"]) >= 6
    assert any("pizza" in k for k in body["keywords"])
    # 60 words / 2.4 wps = 25s → ceil(25 / 2.25) = 12 segments.
    assert body["segments_needed"] == 12
    assert body["duration_s"] == pytest.approx(25.0)
    assert len(body["clips"]) > 0


def test_auto_select_seed_reshuffles_picks(monkeypatch):
    pool = {"kw": [_clip("pexels", f"kw-{i}", "kw") for i in range(10)]}
    _patch_providers(monkeypatch, FakeMontageProvider(pool))

    def run(seed):
        resp = client.post(
            "/api/v1/stock/auto-select",
            json={
                "keywords": ["kw"],
                "duration_s": 9.0,
                "segment_s": 3.0,
                "seed": seed,
            },
        )
        assert resp.status_code == 200
        return [c["id"] for c in resp.json()["clips"]]

    picks_a = run(1)
    picks_b = run(2)
    assert len(picks_a) == 3  # 9s / 3s = 3 clips
    assert picks_a != picks_b  # fresh seed → fresh picks
    assert run(1) == picks_a  # same seed → reproducible


def test_auto_select_exclude_skips_picked_clips(monkeypatch):
    """The swap flow: excluded clips never come back."""
    pool = {"kw": [_clip("pexels", f"kw-{i}", "kw") for i in range(5)]}
    _patch_providers(monkeypatch, FakeMontageProvider(pool))

    resp = client.post(
        "/api/v1/stock/auto-select",
        json={
            "keywords": ["kw"],
            "duration_s": 3.0,
            "segment_s": 3.0,
            "exclude": [
                {"provider": "pexels", "id": "kw-0", "url": "u",
                 "duration_s": 8.0},
                {"provider": "pexels", "id": "kw-1", "url": "u",
                 "duration_s": 8.0},
            ],
        },
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["clips"]]
    assert "kw-0" not in ids and "kw-1" not in ids
    assert ids == ["kw-2"]


def test_auto_select_skips_too_short_clips(monkeypatch):
    pool = {
        "kw": [
            _clip("pexels", "short", "kw", duration_s=1.0),  # < 2s floor
            _clip("pexels", "good", "kw", duration_s=6.0),
        ]
    }
    _patch_providers(monkeypatch, FakeMontageProvider(pool))

    resp = client.post(
        "/api/v1/stock/auto-select",
        json={"keywords": ["kw"], "duration_s": 3.0, "segment_s": 3.0},
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["clips"]]
    assert ids == ["good"]


def test_auto_select_provider_failure_degrades(monkeypatch):
    """One provider blowing up doesn't kill the selection."""
    _patch_providers(
        monkeypatch,
        FakeMontageProvider({}, fail=True),
        FakeMontageProvider({"kw": [_clip("pixabay", "px-7", "kw")]}),
    )
    resp = client.post(
        "/api/v1/stock/auto-select",
        json={"keywords": ["kw"], "duration_s": 3.0, "segment_s": 3.0},
    )
    assert resp.status_code == 200
    clips = resp.json()["clips"]
    assert len(clips) == 1
    assert clips[0]["provider"] == "pixabay"


def test_auto_select_caps_unique_clips(monkeypatch):
    """A huge duration still picks at most STOCK_MAX_MONTAGE_CLIPS clips."""
    pool = {
        f"kw{i}": [_clip("pexels", f"kw{i}-{j}", f"kw{i}") for j in range(6)]
        for i in range(12)
    }
    _patch_providers(monkeypatch, FakeMontageProvider(pool))

    resp = client.post(
        "/api/v1/stock/auto-select",
        json={
            "keywords": list(pool),
            "duration_s": 590.0,
            "segment_s": 1.5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["segments_needed"] == 394
    assert len(body["clips"]) == settings.STOCK_MAX_MONTAGE_CLIPS


def test_auto_select_unkeyed_demo_notice(monkeypatch):
    """Unkeyed providers answer with curated demo clips + a notice."""
    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "")

    resp = client.post(
        "/api/v1/stock/auto-select",
        json={
            "keywords": ["city night walk"],
            "duration_s": 9.0,
            "segment_s": 3.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["clips"]) > 0
    assert "PEXELS_API_KEY" in body["notice"]
    providers = {p["id"]: p["keyed"] for p in body["providers"]}
    assert providers == {"pexels": False, "pixabay": False}


def test_auto_select_client_key_no_demo_notice(monkeypatch):
    """A valid vault key wins: no demo clips in the montage, no notice.

    Regression test: with a live Pexels key and no Pixabay key, the
    montage used to surface the "add PIXABAY_API_KEY" banner even
    though real Pexels clips were fetched.
    """
    from app.providers.stock import pexels as pexels_module

    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "")
    payload = {
        "videos": [
            {
                "id": vid,
                "duration": 12,
                "image": f"https://img/{vid}.jpg",
                "user": {"name": "Ann"},
                "video_files": [
                    {"link": f"https://cdn/{vid}.mp4", "width": 1080,
                     "height": 1920, "quality": "hd"}
                ],
            }
            for vid in (101, 102, 103)
        ]
    }
    factory = _make_fake_client(
        pexels_module, payload, "api.pexels.com/videos/search"
    )
    monkeypatch.setattr(pexels_module.httpx, "AsyncClient", factory)
    resp = client.post(
        "/api/v1/stock/auto-select",
        json={
            "keywords": ["noodles", "city night", "kitchen"],
            "duration_s": 9.0,
            "segment_s": 3.0,
            "pexels_api_key": "vault-pexels",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["notice"] is None
    assert len(body["clips"]) == 3
    assert all(c["provider"] == "pexels" for c in body["clips"])


def test_auto_select_rejects_empty_request():
    resp = client.post("/api/v1/stock/auto-select", json={})
    assert resp.status_code == 422
    assert "keywords" in resp.json()["detail"].lower()


def test_auto_select_no_clips_is_502(monkeypatch):
    _patch_providers(monkeypatch, FakeMontageProvider({}))
    resp = client.post(
        "/api/v1/stock/auto-select",
        json={"keywords": ["nothing"], "duration_s": 3.0, "segment_s": 3.0},
    )
    assert resp.status_code == 502


# --- Render validation: montage clip caps -----------------------------------------


def _clip_payloads(count: int):
    return [
        {
            "provider": "pexels",
            "id": str(i),
            "url": f"https://cdn/{i}.mp4",
            "duration_s": 5.0,
        }
        for i in range(count)
    ]


def test_render_montage_allows_more_clips(monkeypatch):
    """stock_montage raises the clip cap (1.5-3s cuts → more clips)."""
    from app.services.rendering import renderer as renderer_module

    async def noop(job_id, request):
        return None

    monkeypatch.setattr(renderer_module, "run_render_job", noop)
    count = settings.STOCK_MAX_CLIPS + 5  # over the playlist cap
    assert count <= settings.STOCK_MAX_MONTAGE_CLIPS
    resp = client.post(
        "/api/v1/render",
        json={
            "script": ["hello"],
            "stock_clips": _clip_payloads(count),
            "stock_montage": True,
        },
    )
    assert resp.status_code == 200


def test_render_rejects_too_many_montage_clips(monkeypatch):
    count = settings.STOCK_MAX_MONTAGE_CLIPS + 1
    resp = client.post(
        "/api/v1/render",
        json={
            "script": ["hello"],
            "stock_clips": _clip_payloads(count),
            "stock_montage": True,
        },
    )
    assert resp.status_code == 400
    assert "Too many stock clips" in resp.json()["detail"]
