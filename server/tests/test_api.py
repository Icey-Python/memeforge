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


def test_generate_script_duration_targets():
    """60s default ≈ 130-150 words; 30s paces to roughly half."""

    def words(payload):
        resp = client.post("/api/v1/generate-script", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        word_count = sum(len(line["text"].split()) for line in body["lines"])
        return word_count, len(body["lines"])

    w30, l30 = words({"topic": "elden ring", "provider": "mock", "duration_target": 30})
    w60, l60 = words(
        {"topic": "elden ring", "provider": "mock", "duration_target": 60}
    )
    w90, l90 = words(
        {"topic": "elden ring", "provider": "mock", "duration_target": 90}
    )

    # Word budget scales with the duration target (2.2-2.5 words/sec).
    assert 60 <= w30 <= 90  # ~70 words
    assert 120 <= w60 <= 160  # ~141 words (the classic short-form pacing)
    assert w90 >= w60 > w30
    # Line pacing: ~4s of speech per line (capped by max_lines default).
    assert l30 < l60 <= 15 <= l90


def test_generate_script_rejects_bad_duration_target():
    resp = client.post(
        "/api/v1/generate-script",
        json={"topic": "x", "provider": "mock", "duration_target": 5},
    )
    assert resp.status_code == 422


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


def test_render_rejects_unknown_card_style():
    resp = client.post(
        "/api/v1/render",
        json={
            "script": ["hello", "world"],
            "gameplay_id": "does-not-exist",
            "card_style": "nope",
        },
    )
    assert resp.status_code == 422  # pydantic enum validation


def test_voices_default_edge():
    resp = client.get("/api/v1/voices")
    assert resp.status_code == 200
    assert len(resp.json()) > 0
    # Voices carry category tags; popular meme neural voices are pre-tagged.
    voices = resp.json()
    assert all("tags" in v for v in voices)
    meme_ids = {v["id"] for v in voices if "meme" in v["tags"]}
    assert {
        "en-US-ChristopherNeural",
        "en-US-GuyNeural",
        "en-US-EricNeural",
        "en-US-JennyNeural",
    } <= meme_ids


def test_voices_tiktok_meme_catalog():
    resp = client.get("/api/v1/voices", params={"provider": "tiktok"})
    assert resp.status_code == 200
    voices = resp.json()
    ids = {v["id"] for v in voices}
    assert {
        "en_us_002",  # Jessie
        "en_male_cody",  # Serious Male
        "en_male_narration",  # Narrator
        "en_us_ghostface",  # Ghostface
        "en_us_trickster",  # Trickster
    } <= ids
    assert all("meme" in v["tags"] for v in voices)


def test_voices_meme_classic_catalog():
    resp = client.get("/api/v1/voices", params={"provider": "meme_classic"})
    assert resp.status_code == 200
    voices = resp.json()
    ids = {v["id"] for v in voices}
    # The iconic free meme cast (ttsmp3 / Polly voices).
    assert {
        "Brian",  # THE meme voice
        "Justin",  # kid/teen
        "Matthew",  # deep narrator
        "Kendra",
        "Salli",
        "Joey",
        "Ivy",
        "Joanna",
    } <= ids
    assert voices[0]["id"] == "Brian"
    assert all("meme" in v["tags"] for v in voices)


def test_voices_google_catalog():
    resp = client.get("/api/v1/voices", params={"provider": "google"})
    assert resp.status_code == 200
    voices = resp.json()
    ids = {v["id"] for v in voices}
    assert {"en", "en-GB", "en-AU"} <= ids  # tl language codes


def test_voices_unknown_provider_400():
    resp = client.get("/api/v1/voices", params={"provider": "nope"})
    assert resp.status_code == 422  # pydantic enum validation


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


# --- Per-request credential pass-through (plug-and-play keys) -----------------


def test_tts_endpoint_uses_request_api_key(monkeypatch):
    """POST /tts with an api_key override works with no server .env key."""
    from app.providers.tts import elevenlabs as elevenlabs_module
    from app.core import settings as app_settings

    monkeypatch.setattr(app_settings, "ELEVENLABS_API_KEY", "")

    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(elevenlabs_module.httpx, "AsyncClient", FakeClient)

    resp = client.post(
        "/api/v1/tts",
        json={
            "text": "hello",
            "provider": "elevenlabs",
            "voice": "21m00Tcm4TlvDq8ikWAM",
            "api_key": "sk-from-ui",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_url"].startswith("/outputs/tts-")
    # The request key (not the empty server .env) authenticated the call.
    assert captured["headers"]["xi-api-key"] == "sk-from-ui"


def test_voices_endpoint_uses_request_api_key(monkeypatch):
    """GET /voices with api_key lists the ElevenLabs library keylessly."""
    from app.providers.tts import elevenlabs as elevenlabs_module

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "voices": [
                    {
                        "voice_id": "vr-1",
                        "name": "Rachel",
                        "labels": {"language": "en", "gender": "female"},
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

        async def get(self, url, headers=None):
            assert headers["xi-api-key"] == "sk-from-ui"
            return FakeResponse()

    monkeypatch.setattr(elevenlabs_module.httpx, "AsyncClient", FakeClient)

    resp = client.get(
        "/api/v1/voices",
        params={"provider": "elevenlabs", "api_key": "sk-from-ui"},
    )
    assert resp.status_code == 200
    voices = resp.json()
    assert voices[0]["id"] == "vr-1"
    assert voices[0]["label"] == "Rachel"


def test_render_request_accepts_tts_credentials():
    """Render payloads carry the vault's TTS credentials to the job."""
    from app.schemas.render_schema import RenderRequest
    from app.services.rendering.renderer import build_tts_provider

    request = RenderRequest(
        script=["hello"],
        gameplay_id="minecraft-parkour",
        tts_provider="azure",
        tts_api_key="k-from-ui",
        tts_region="eastus",
    )
    provider = build_tts_provider(request)
    assert provider.is_configured() is True
    assert provider.api_key == "k-from-ui"
    assert provider.region == "eastus"

    # Defaults stay None (fall back to the server .env).
    bare = RenderRequest(script=["hello"], gameplay_id="minecraft-parkour")
    assert bare.tts_api_key is None
    assert bare.tts_region is None
