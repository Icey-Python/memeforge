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


def test_models_catalog():
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    providers = {p["id"]: p for p in resp.json()}
    assert set(providers) == {"openai", "ollama", "mock"}
    assert providers["ollama"]["default_model"]


def test_generate_script_forwards_base_url_override():
    """base_url overrides reach the connector (unreachable Ollama -> 502)."""
    resp = client.post(
        "/api/v1/generate-script",
        json={
            "topic": "elden ring",
            "provider": "ollama",
            "base_url": "http://127.0.0.1:1",
        },
    )
    assert resp.status_code == 502
    assert "Script generation failed" in resp.json()["detail"]


def test_discover_models_mock():
    resp = client.post("/api/v1/models/discover", json={"provider": "mock"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["provider"] == "mock"
    assert [m["id"] for m in body["models"]] == ["memeforge-stub"]


def test_discover_models_rejects_unknown_provider():
    resp = client.post("/api/v1/models/discover", json={"provider": "nope"})
    assert resp.status_code == 422


def test_discover_models_ollama_unreachable():
    """A dead endpoint reports reachable=False (200) with a helpful error."""
    resp = client.post(
        "/api/v1/models/discover",
        json={"provider": "ollama", "base_url": "http://127.0.0.1:1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is False
    assert body["models"] == []
    assert "http://127.0.0.1:1" in body["error"]


def test_discover_models_ollama_parses_tags(monkeypatch):
    """Ollama /api/tags payloads map onto the discovery response."""
    from app.providers.llm import ollama as ollama_module

    payload = {
        "models": [
            {
                "name": "llama3.2:latest",
                "size": 2_019_393_188,
                "modified_at": "2024-09-06T17:39:40.74838Z",
                "details": {
                    "family": "llama",
                    "parameter_size": "3.2B",
                    "quantization_level": "Q4_K_M",
                },
            },
            # `name` missing -> falls back to the `model` field
            {"model": "qwen2.5:0.5b", "details": {"family": "qwen2"}},
        ]
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            assert url == "http://ollama.local:11434/api/tags"
            return FakeResponse()

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", FakeClient)

    resp = client.post(
        "/api/v1/models/discover",
        json={"provider": "ollama", "base_url": "http://ollama.local:11434"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["base_url"] == "http://ollama.local:11434"
    assert [m["id"] for m in body["models"]] == [
        "llama3.2:latest",
        "qwen2.5:0.5b",
    ]
    llama = body["models"][0]
    assert llama["parameter_size"] == "3.2B"
    assert llama["quantization"] == "Q4_K_M"
    assert llama["size_bytes"] == 2_019_393_188


def test_discover_models_openai_parses_model_list(monkeypatch):
    """OpenAI-compatible GET /models payloads map onto the discovery response."""
    from app.providers.llm import openai_compatible as openai_module

    payload = {
        "data": [
            {"id": "gpt-4o-mini", "owned_by": "openai"},
            {"id": "gpt-4o", "owned_by": "openai"},
        ]
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            assert url == "https://api.openai.com/v1/models"
            return FakeResponse()

    monkeypatch.setattr(openai_module.httpx, "AsyncClient", FakeClient)

    resp = client.post(
        "/api/v1/models/discover",
        json={"provider": "openai", "base_url": "https://api.openai.com/v1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    # models are sorted for a stable dropdown order
    assert [m["id"] for m in body["models"]] == ["gpt-4o", "gpt-4o-mini"]
    assert body["models"][0]["family"] == "openai"


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
