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
    videos = [v for v in resp.json()["videos"] if not v["is_demo"]]
    assert len(videos) == 1
    v = videos[0]
    assert v["id"] == "123"
    assert v["provider"] == "pexels"
    assert v["video_url"] == "https://cdn/x-port.mp4"
    assert v["duration_s"] == 9.0
    assert v["author"] == "Ada"
    assert v["thumbnail_url"].endswith("pic.jpg")
    # Pixabay stays unkeyed in this test → demo notice mentions only it.
    assert "PIXABAY_API_KEY" in resp.json()["notice"]


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
    assert "trim=duration=8.000" in joined
    assert "trim=duration=3.000" in joined
    # Normalized to the render canvas, audio dropped.
    assert "scale=1080:1920" in joined
    assert "-an" in args
    assert str(tmp_path / "out.mp4") in args


def test_stitch_background_args_single_clip(tmp_path):
    clips = [(tmp_path / "a.mp4", 9.0)]
    args = stitcher.stitch_background_args(clips, tmp_path / "out.mp4", 4.0)
    joined = " ".join(args)
    assert "concat=n=" not in joined
    assert "trim=duration=4.000" in joined


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
