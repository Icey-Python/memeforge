"""Smoke tests: app import, health route, catalogs, and providers offline."""

from fastapi.testclient import TestClient

from app.main import app
from app.providers.llm.mock import MockLLMProvider

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "ffmpeg" in body["capabilities"]


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["msg"].startswith("Memeforge")


def test_generate_script_mock():
    resp = client.post(
        "/api/v1/generate-script",
        json={"topic": "elden ring", "provider": "mock", "max_lines": 4},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["lines"]) == 4
    assert body["lines"][-1]["is_punchline"] is True


def test_gameplay_catalog():
    resp = client.get("/api/v1/render/gameplays")
    assert resp.status_code == 200
    ids = {clip["id"] for clip in resp.json()}
    assert {"minecraft-parkour", "subway-surfers", "gta5-stunts"} <= ids


def test_render_rejects_unavailable_gameplay():
    resp = client.post(
        "/api/v1/render",
        json={
            "script": ["hello", "world"],
            "gameplay_id": "does-not-exist",
        },
    )
    assert resp.status_code == 400


def test_voices_default_edge():
    resp = client.get("/api/v1/voices")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_caption_timeline():
    from app.services.rendering.captions import build_caption_timeline

    frames = build_caption_timeline(
        ["one two three four"], [2.0], punchline_indexes={0}
    )
    # 4 words / 2 words-per-frame = 2 frames
    assert len(frames) == 2
    assert frames[-1].end == 2.0
    assert frames[-1].is_punchline


def test_mock_provider_is_configured():
    assert MockLLMProvider().is_configured() is True
