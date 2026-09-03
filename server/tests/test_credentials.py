"""Client credential pass-through tests (studio key vault flow).

The studio keeps API keys in an encrypted browser vault and sends them
with each request. These tests pin the backend contract: client-supplied
credentials (request body / headers / query params) take priority over
the server .env defaults on every endpoint that uses keyed providers.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import settings
from app.main import app
from app.providers.llm.registry import get_llm_provider
from app.providers.tts.elevenlabs import ElevenLabsProvider
from app.providers.tts.azure import AzureTTSProvider
from app.providers.tts.registry import get_tts_provider

client = TestClient(app)


# --- Fake httpx plumbing -----------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.headers = {}
        self.content = b"mp3-bytes"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")

    def json(self):
        return self.payload


class RecordingClient:
    """Async httpx fake that records requests into a shared call list."""

    def __init__(self, payload, calls):
        self.payload = payload
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(self.payload)

    async def post(self, url, json=None, headers=None, content=None):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "content": content}
        )
        if self.payload is not None:
            return FakeResponse(self.payload)
        return FakeResponse({})


def _fake_async_client(payload=None):
    """Patched httpx.AsyncClient factory + the shared recorded-calls list."""
    calls: list = []

    def factory(**kwargs):
        return RecordingClient(payload, calls)

    return factory, calls


# --- TTS: request-body keys reach the providers -------------------------------


def test_tts_provider_uses_client_elevenlabs_key_over_env(monkeypatch):
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "server-env-key")
    provider = get_tts_provider("elevenlabs", elevenlabs_api_key="vault-key")
    assert isinstance(provider, ElevenLabsProvider)
    assert provider.api_key == "vault-key"  # client key wins


def test_tts_provider_falls_back_to_env_elevenlabs_key(monkeypatch):
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "server-env-key")
    provider = get_tts_provider("elevenlabs")
    assert provider.api_key == "server-env-key"


def test_tts_provider_uses_client_azure_credentials(monkeypatch):
    monkeypatch.setattr(settings, "AZURE_SPEECH_KEY", "server-key")
    monkeypatch.setattr(settings, "AZURE_SPEECH_REGION", "westeurope")
    provider = get_tts_provider(
        "azure",
        azure_speech_key="vault-key",
        azure_speech_region="eastus",
    )
    assert isinstance(provider, AzureTTSProvider)
    assert provider.speech_key == "vault-key"
    assert provider.region == "eastus"  # both client values win


def test_tts_endpoint_forwards_elevenlabs_key(monkeypatch):
    """POST /tts sends the vault key in the xi-api-key header upstream."""
    from app.providers.tts import elevenlabs as elevenlabs_module

    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "")
    factory, calls = _fake_async_client(None)
    monkeypatch.setattr(elevenlabs_module.httpx, "AsyncClient", factory)
    resp = client.post(
        "/api/v1/tts",
        json={
            "text": "hello",
            "provider": "elevenlabs",
            "elevenlabs_api_key": "vault-key",
        },
    )
    assert resp.status_code == 200
    assert calls[0]["headers"]["xi-api-key"] == "vault-key"


def test_voices_endpoint_forwards_elevenlabs_key_via_query(monkeypatch):
    """GET /voices lists the account's ElevenLabs library with a vault key."""
    from app.providers.tts import elevenlabs as elevenlabs_module

    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "")
    factory, calls = _fake_async_client({"voices": [{"voice_id": "21m00", "name": "Rachel"}]})
    monkeypatch.setattr(elevenlabs_module.httpx, "AsyncClient", factory)
    resp = client.get(
        "/api/v1/voices",
        params={"provider": "elevenlabs", "elevenlabs_api_key": "vault-key"},
    )
    assert resp.status_code == 200
    assert [v["id"] for v in resp.json()] == ["21m00"]
    assert calls[0]["headers"]["xi-api-key"] == "vault-key"


def test_voices_endpoint_accepts_header_credentials(monkeypatch):
    """GET /voices also accepts the vault keys as X-... headers."""
    from app.providers.tts import elevenlabs as elevenlabs_module

    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "")
    factory, calls = _fake_async_client({"voices": []})
    monkeypatch.setattr(elevenlabs_module.httpx, "AsyncClient", factory)
    resp = client.get(
        "/api/v1/voices",
        params={"provider": "elevenlabs"},
        headers={"X-Elevenlabs-Key": "header-key"},
    )
    assert resp.status_code == 200
    assert calls[0]["headers"]["xi-api-key"] == "header-key"


# --- Stock: client keys enable live search without server .env ----------------


def test_stock_search_client_pexels_key_beats_env(monkeypatch):
    """A vault Pexels key triggers live search even with no server .env key."""
    from app.providers.stock import pexels as pexels_module

    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    payload = {
        "videos": [
            {
                "id": 123,
                "duration": 12,
                "image": "https://img/x.jpg",
                "user": {"name": "Ann"},
                "video_files": [
                    {"link": "https://cdn/x.mp4", "width": 1080, "height": 1920,
                     "quality": "hd"}
                ],
            }
        ]
    }
    factory, calls = _fake_async_client(payload)
    monkeypatch.setattr(pexels_module.httpx, "AsyncClient", factory)
    resp = client.get(
        "/api/v1/stock/search",
        params={
            "q": "noodles",
            "pexels_api_key": "vault-pexels",
            "pixabay_api_key": "vault-pixabay",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Both providers are keyed by the client: no demo clips, no notice.
    assert all(not v["is_demo"] for v in body["videos"])
    assert body["notice"] is None
    assert calls[0]["headers"]["Authorization"] == "vault-pexels"  # pexels first
    # The provider catalog reports the *effective* key state.
    assert {p["id"]: p["keyed"] for p in body["providers"]}["pexels"] is True


def test_stock_search_client_pixabay_key_via_header(monkeypatch):
    """Pixabay vault keys can arrive as X-Pixabay-Key headers too."""
    from app.providers.stock import pixabay as pixabay_module

    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "")
    payload = {
        "hits": [
            {
                "id": 9,
                "duration": 8,
                "picture_id": "pic",
                "user": "Bob",
                "tags": "city, night",
                "videos": {
                    "large": {"url": "https://cdn/9.mp4", "width": 1080,
                              "height": 1920}
                },
            }
        ]
    }
    factory, calls = _fake_async_client(payload)
    monkeypatch.setattr(pixabay_module.httpx, "AsyncClient", factory)
    resp = client.get(
        "/api/v1/stock/search",
        params={"q": "city"},
        headers={"X-Pixabay-Key": "vault-pixabay"},
    )
    assert resp.status_code == 200
    body = resp.json()
    pixabay_videos = [v for v in body["videos"] if v["provider"] == "pixabay"]
    assert len(pixabay_videos) == 1
    assert pixabay_videos[0]["is_demo"] is False
    assert calls[0]["params"]["key"] == "vault-pixabay"


def test_stock_search_unkeyed_still_falls_back_to_demos(monkeypatch):
    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "")
    resp = client.get("/api/v1/stock/search", params={"q": "noodles"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(v["is_demo"] for v in body["videos"])
    assert "demo" in body["notice"].lower()


# --- LLM: gateway env defaults + request-key priority -------------------------


def test_llm_registry_gateway_env_key_by_base_url(monkeypatch):
    """OpenRouter/Groq/Anthropic base URLs pick their matching env key."""
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-env-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-env-key")
    provider = get_llm_provider(
        "openai", base_url="https://openrouter.ai/api/v1"
    )
    assert provider.api_key == "or-env-key"


def test_llm_registry_request_key_beats_gateway_env(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-env-key")
    provider = get_llm_provider(
        "openai", base_url="https://openrouter.ai/api/v1", api_key="vault-key"
    )
    assert provider.api_key == "vault-key"


def test_llm_registry_generic_url_falls_back_to_openai_env(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-env-key")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-env-key")
    provider = get_llm_provider(
        "openai", base_url="https://api.openai.com/v1"
    )
    assert provider.api_key == "openai-env-key"


# --- Render: TTS credentials ride on the render request -----------------------


def test_render_request_accepts_tts_credentials():
    """The render schema carries the vault keys for the background job."""
    from app.schemas.render_schema import RenderRequest

    request = RenderRequest(
        script=["line one", "line two"],
        tts_provider="elevenlabs",
        elevenlabs_api_key="vault-key",
        azure_speech_region="eastus",
    )
    assert request.elevenlabs_api_key == "vault-key"
    assert request.azure_speech_region == "eastus"


def test_render_forwards_tts_credentials_to_provider(monkeypatch):
    """The render job builds its TTS provider with the client credentials."""
    from app.providers.tts import registry as tts_registry_module
    from app.schemas.render_schema import RenderRequest, StockClipRef
    from app.services import jobs as jobs_service
    from app.services.rendering import renderer

    captured: dict = {}
    original = tts_registry_module.get_tts_provider

    def spy(name, voice=None, elevenlabs_api_key=None, azure_speech_key=None,
            azure_speech_region=None):
        captured.update(
            elevenlabs=elevenlabs_api_key,
            azure_key=azure_speech_key,
            azure_region=azure_speech_region,
        )
        return original(name, voice=voice)

    monkeypatch.setattr(tts_registry_module, "get_tts_provider", spy)

    async def _stop(provider, text):
        raise RuntimeError("stop the job right after the provider is built")

    monkeypatch.setattr(renderer, "_synthesize_with_retry", _stop)

    request = RenderRequest(
        script=["line"],
        tts_provider="elevenlabs",
        elevenlabs_api_key="vault-key",
        # A stock-clip background skips gameplay asset resolution; the
        # downloads only start after TTS, which we abort on purpose.
        stock_clips=[
            StockClipRef(
                provider="pexels", id="1", url="https://x/1.mp4", duration_s=5.0
            )
        ],
    )
    job = jobs_service.job_store.create()
    import asyncio

    asyncio.run(renderer.run_render_job(job.job_id, request))
    assert captured["elevenlabs"] == "vault-key"
    assert jobs_service.job_store.get(job.job_id).status.value == "failed"


# --- Health: server-default key presence report -------------------------------


def test_health_reports_server_key_capabilities():
    resp = client.get("/health")
    assert resp.status_code == 200
    caps = resp.json()["capabilities"]
    for flag in (
        "llm_openai",
        "llm_openrouter",
        "llm_groq",
        "llm_anthropic",
        "tts_elevenlabs",
        "tts_azure",
        "tts_azure_region",
        "stock_pexels",
        "stock_pixabay",
    ):
        assert isinstance(caps[flag], bool)
