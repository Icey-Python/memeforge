"""Fish Audio TTS provider tests (mocked HTTP — no network).

Covers the SSE timestamp stream (primary path), the batch fallback,
word-timing assembly with global offsets, the concurrency semaphore,
credential pass-through (client vault key > server .env), the curated
voice shortlist + live marketplace mapping, and the HTTP endpoints.
"""

import asyncio
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import settings
from app.main import app
from app.providers.tts import fish as fish_module
from app.providers.tts.fish import (
    FishAudioTTSProvider,
    _assemble_sse_stream,
    _parse_sse_data_line,
    _rate_to_speed,
)
from app.providers.tts.registry import (
    _REGISTRY,
    get_tts_provider,
    list_tts_voices,
)

client = TestClient(app)


# --- Fake httpx plumbing -----------------------------------------------------


class FakeStreamResponse:
    """Stand-in for an httpx streaming response (SSE lines)."""

    def __init__(self, lines=None, status_code=200, body=b""):
        self.lines = lines or []
        self.status_code = status_code
        self._body = body

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class FakeResponse:
    """Stand-in for a buffered httpx response."""

    def __init__(self, payload=None, status_code=200, content=b""):
        self.payload = payload
        self.status_code = status_code
        self.content = content
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")

    def json(self):
        return self.payload if self.payload is not None else {}


class _Ctx:
    """Async context manager wrapper for client.stream()."""

    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *args):
        return None


class FakeFishClient:
    """httpx.AsyncClient fake recording stream()/post()/get() calls."""

    def __init__(self, stream_resp=None, post_resp=None, get_resp=None):
        self.calls: list = []
        self.stream_resp = stream_resp or FakeStreamResponse()
        self.post_resp = post_resp or FakeResponse()
        self.get_resp = get_resp or FakeResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, method, url, **kwargs):
        self.calls.append({"kind": "stream", "method": method, "url": url, **kwargs})
        return _Ctx(self.stream_resp)

    async def post(self, url, **kwargs):
        self.calls.append({"kind": "post", "url": url, **kwargs})
        return self.post_resp

    async def get(self, url, params=None, headers=None):
        self.calls.append(
            {"kind": "get", "url": url, "params": params, "headers": headers}
        )
        return self.get_resp


def _patch_fish_http(monkeypatch, fake_client: FakeFishClient) -> FakeFishClient:
    """Point the provider's httpx.AsyncClient at the fake."""

    def factory(**kwargs):
        return fake_client

    monkeypatch.setattr(fish_module.httpx, "AsyncClient", factory)
    return fake_client


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}"


@pytest.fixture(autouse=True)
def _reset_fish_semaphore():
    """Keep the module-global semaphore from leaking between tests."""
    yield
    fish_module._semaphore = None
    fish_module._semaphore_loop_id = None


# --- Registry & configuration -------------------------------------------------


def test_registry_includes_fish_audio():
    assert _REGISTRY["fish_audio"] is FishAudioTTSProvider
    provider = get_tts_provider("fish_audio")
    assert isinstance(provider, FishAudioTTSProvider)
    assert provider.name == "fish_audio"
    assert provider.model == "s2.1-pro"  # recommended production model
    # Unconfigured voice -> the official narrator (a stable marketplace
    # id; an omitted reference_id would randomize the speaker per line).
    assert provider.voice == fish_module.FISH_NARRATOR_VOICE


def test_fish_model_selection_and_validation():
    provider = get_tts_provider("fish_audio", fish_model="s2.1-pro-free")
    assert provider.model == "s2.1-pro-free"  # zero-cost trial model
    provider = get_tts_provider("fish_audio", fish_model="s1")
    assert provider.model == "s1"
    with pytest.raises(ValueError, match="Unknown Fish Audio model"):
        get_tts_provider("fish_audio", fish_model="s3-ultra")


def test_fish_client_key_takes_priority_over_env(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "server-env-key")
    provider = get_tts_provider("fish_audio", fish_api_key="vault-key")
    assert provider.api_key == "vault-key"  # client key wins
    provider = get_tts_provider("fish_audio")
    assert provider.api_key == "server-env-key"  # env fallback


def test_fish_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    provider = FishAudioTTSProvider()
    assert provider.is_configured() is False
    with pytest.raises(RuntimeError, match="requires FISH_API_KEY"):
        asyncio.run(provider.synthesize("hello"))


@pytest.mark.asyncio
async def test_fish_empty_text_raises(monkeypatch):
    provider = FishAudioTTSProvider(api_key="k")
    fake = _patch_fish_http(monkeypatch, FakeFishClient())
    with pytest.raises(ValueError, match="empty text"):
        await provider.synthesize("   ")
    assert fake.calls == []  # no HTTP call for empty text


# --- Rate -> prosody speed mapping ---------------------------------------------


def test_rate_to_speed():
    assert _rate_to_speed("+0%") is None  # neutral: omit prosody
    assert _rate_to_speed("+20%") == pytest.approx(1.2)
    assert _rate_to_speed("-50%") == pytest.approx(0.5)
    assert _rate_to_speed("+400%") == pytest.approx(2.0)  # clamped to Fish range
    assert _rate_to_speed("nonsense") is None
    assert _rate_to_speed("") is None


# --- SSE parsing ----------------------------------------------------------------


def test_parse_sse_data_line():
    event = {"audio_base64": "abc", "chunk_seq": 0}
    assert _parse_sse_data_line(f"data: {json.dumps(event)}") == event
    assert _parse_sse_data_line('data:  {"a": 1}') == {"a": 1}  # extra space
    assert _parse_sse_data_line("event: message") is None  # not a data line
    assert _parse_sse_data_line("") is None
    assert _parse_sse_data_line(": keepalive") is None
    assert _parse_sse_data_line("data: not-json") is None
    assert _parse_sse_data_line("data: [DONE]") is None


def test_assemble_sse_stream_offsets_and_snapshots():
    """Chunk offsets shift local segments onto the global timeline and
    later alignment snapshots for a chunk replace earlier ones."""
    events = [
        # chunk 0: first audio + partial alignment snapshot
        {
            "audio_base64": _b64(b"mp3-a"),
            "chunk_seq": 0,
            "chunk_audio_offset_sec": 0.0,
            "alignment": {
                "audio_duration": 0.5,
                "segments": [{"text": "brace", "start": 0.0, "end": 0.4}],
            },
        },
        # chunk 0: cumulative snapshot replaces the partial one
        {
            "audio_base64": _b64(b"mp3-b"),
            "chunk_seq": 0,
            "chunk_audio_offset_sec": 0.0,
            "alignment": {
                "audio_duration": 0.8,
                "segments": [
                    {"text": "brace", "start": 0.0, "end": 0.4},
                    {"text": "yourself", "start": 0.4, "end": 0.8},
                ],
            },
        },
        # chunk 1: local segment times offset by the chunk position
        {
            "audio_base64": _b64(b"mp3-c"),
            "chunk_seq": 1,
            "chunk_audio_offset_sec": 0.8,
            "alignment": {
                "audio_duration": 0.6,
                "segments": [{"text": "before", "start": 0.0, "end": 0.6}],
            },
        },
    ]
    audio, timings = _assemble_sse_stream(events)
    assert audio == b"mp3-amp3-bmp3-c"
    assert [(t.text, t.start, t.end) for t in timings] == [
        ("brace", 0.0, 0.4),
        ("yourself", 0.4, 0.8),
        ("before", 0.8, 1.4),  # 0.0 local + 0.8 chunk offset
    ]


def test_assemble_sse_drops_unusable_segments():
    events = [
        {
            "audio_base64": _b64(b"mp3"),
            "chunk_seq": 0,
            "chunk_audio_offset_sec": 0.0,
            "alignment": {
                "segments": [
                    {"text": "hello", "start": 0.0, "end": 0.3},
                    {"text": ",", "start": 0.3, "end": 0.35},  # punctuation-only
                    {"text": "world", "start": 0.35, "end": 0.7},
                    {"text": "", "start": 0.7, "end": 0.9},  # empty
                    {"text": "bad", "start": 0.9},  # missing end
                    {"text": "rev", "start": 0.9, "end": 0.8},  # end <= start
                ]
            },
        }
    ]
    audio, timings = _assemble_sse_stream(events)
    assert audio == b"mp3"
    assert [(t.text, t.start, t.end) for t in timings] == [
        ("hello", 0.0, 0.3),
        ("world", 0.35, 0.7),
    ]


# --- Synthesis: SSE (primary) + batch (fallback) --------------------------------


@pytest.mark.asyncio
async def test_synthesize_sse_with_word_timings(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    provider = FishAudioTTSProvider(
        api_key="vault-key", voice="abc123", model="s2.1-pro"
    )
    lines = [
        _sse(
            {
                "audio_base64": _b64(b"fish-mp3-part1"),
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
                "alignment": {
                    "audio_duration": 0.9,
                    "segments": [
                        {"text": "this", "start": 0.0, "end": 0.2},
                        {"text": "is", "start": 0.2, "end": 0.3},
                        {"text": "memeforge", "start": 0.3, "end": 0.9},
                    ],
                },
            }
        ),
        _sse({"audio_base64": _b64(b"part2"), "chunk_seq": 0}),
        "event: keepalive",  # non-data lines are ignored
    ]
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(stream_resp=FakeStreamResponse(lines=lines))
    )

    audio = await provider.synthesize("this is memeforge", rate="+10%")

    assert audio.provider == "fish_audio"
    assert audio.format == "mp3"
    assert audio.voice == "abc123"
    assert audio.audio_bytes == b"fish-mp3-part1part2"
    assert audio.word_timings is not None
    assert [(t.text, t.start, t.end) for t in audio.word_timings] == [
        ("this", 0.0, 0.2),
        ("is", 0.2, 0.3),
        ("memeforge", 0.3, 0.9),
    ]
    # One request only: the SSE endpoint (no batch fallback on success).
    assert [c["kind"] for c in fake.calls] == ["stream"]
    call = fake.calls[0]
    assert call["url"].endswith("/v1/tts/stream/with-timestamp")
    assert call["headers"]["Authorization"] == "Bearer vault-key"
    assert call["headers"]["model"] == "s2.1-pro"
    assert call["headers"]["Accept"] == "text/event-stream"
    assert call["json"]["reference_id"] == "abc123"
    assert call["json"]["format"] == "mp3"
    assert call["json"]["prosody"] == {"speed": pytest.approx(1.1)}


@pytest.mark.asyncio
async def test_falls_back_to_batch_when_stream_unavailable(monkeypatch):
    provider = FishAudioTTSProvider(api_key="k", voice="abc123")
    fake = _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(status_code=404),
            post_resp=FakeResponse(status_code=200, content=b"batch-mp3"),
        ),
    )

    audio = await provider.synthesize("hello world")

    assert audio.audio_bytes == b"batch-mp3"
    assert audio.word_timings is None  # batch endpoint carries no timings
    assert [c["kind"] for c in fake.calls] == ["stream", "post"]
    assert fake.calls[0]["url"].endswith("/v1/tts/stream/with-timestamp")
    assert fake.calls[1]["url"].endswith("/v1/tts")
    # Same request shape on both endpoints (they share the TTSRequest body).
    assert fake.calls[1]["json"] == fake.calls[0]["json"]
    assert fake.calls[1]["headers"]["model"] == "s2.1-pro"


@pytest.mark.asyncio
async def test_falls_back_to_batch_when_stream_yields_no_audio(monkeypatch):
    provider = FishAudioTTSProvider(api_key="k")
    fake = _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(
                lines=[_sse({"chunk_seq": 0, "alignment": {"segments": []}})]
            ),
            post_resp=FakeResponse(status_code=200, content=b"batch-mp3"),
        ),
    )
    audio = await provider.synthesize("hello")
    assert audio.audio_bytes == b"batch-mp3"
    assert audio.word_timings is None


@pytest.mark.asyncio
async def test_default_voice_sends_narrator_reference(monkeypatch):
    """An empty voice resolves to the official narrator: every request
    carries a reference_id so Fish never randomizes the speaker."""
    provider = FishAudioTTSProvider(api_key="k", voice="")
    fake = _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(status_code=405),
            post_resp=FakeResponse(status_code=200, content=b"mp3"),
        ),
    )
    audio = await provider.synthesize("hello")
    assert audio.audio_bytes == b"mp3"
    payload = fake.calls[1]["json"]
    assert payload["reference_id"] == fish_module.FISH_NARRATOR_VOICE
    assert "prosody" not in payload  # neutral rate: omit the field


@pytest.mark.asyncio
async def test_synthesize_unconfigured_voice_uses_narrator(monkeypatch):
    """The SSE (primary) path also rides the narrator reference_id."""
    provider = FishAudioTTSProvider(api_key="k", voice=None)
    fake = _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(
                lines=[_sse({"audio_base64": _b64(b"mp3"), "chunk_seq": 0})]
            )
        ),
    )
    await provider.synthesize("hello")
    assert (
        fake.calls[0]["json"]["reference_id"] == fish_module.FISH_NARRATOR_VOICE
    )


@pytest.mark.asyncio
async def test_stream_auth_error_does_not_fall_back(monkeypatch):
    provider = FishAudioTTSProvider(api_key="bad-key")
    fake = _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(
                status_code=401, body=b'{"message": "invalid api key"}'
            )
        ),
    )
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await provider.synthesize("hello")
    assert [c["kind"] for c in fake.calls] == ["stream"]  # no batch retry


@pytest.mark.asyncio
async def test_batch_error_surfaces_with_status(monkeypatch):
    provider = FishAudioTTSProvider(api_key="k")
    _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(status_code=404),
            post_resp=FakeResponse(status_code=429, content=b"too busy"),
        ),
    )
    with pytest.raises(RuntimeError, match="429"):
        await provider.synthesize("hello")


@pytest.mark.asyncio
async def test_batch_empty_audio_raises(monkeypatch):
    provider = FishAudioTTSProvider(api_key="k")
    _patch_fish_http(
        monkeypatch,
        FakeFishClient(
            stream_resp=FakeStreamResponse(status_code=404),
            post_resp=FakeResponse(status_code=200, content=b""),
        ),
    )
    with pytest.raises(RuntimeError, match="no audio"):
        await provider.synthesize("hello")


# --- Concurrency semaphore --------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_sized_from_env(monkeypatch):
    monkeypatch.setattr(settings, "FISH_CONCURRENCY", 3)
    fish_module._semaphore = None
    fish_module._semaphore_loop_id = None
    assert fish_module._fish_semaphore()._value == 3
    # Degenerate env values clamp to at least one slot.
    monkeypatch.setattr(settings, "FISH_CONCURRENCY", 0)
    fish_module._semaphore = None
    fish_module._semaphore_loop_id = None
    assert fish_module._fish_semaphore()._value == 1


# --- Voice catalogs ----------------------------------------------------------------


def test_list_voices_curated_shortlist():
    voices = FishAudioTTSProvider(api_key="k").list_voices()
    ids = {v.id for v in voices}
    assert fish_module.FISH_NARRATOR_VOICE in ids  # default narrator entry
    assert "90e65eaaf50e4470b8e6d43ee6afd7d5" in ids  # Smash Bros Announcer
    assert voices[0].id == fish_module.FISH_NARRATOR_VOICE  # narrator leads
    assert "" not in ids  # no empty-id entries: every voice is addressable
    assert len(ids) == len(voices)  # no duplicate ids
    assert all(v.language == "en" for v in voices)


@pytest.mark.asyncio
async def test_list_remote_voices_maps_marketplace_entities(monkeypatch):
    provider = FishAudioTTSProvider(api_key="k")
    payload = {
        "total": 2,
        "items": [
            {
                "_id": "id-1",
                "title": "Smash Announcer",
                "languages": ["en"],
                "tags": ["male", "character-voice"],
            },
            {
                "_id": "id-2",
                "title": "Sarah",
                "languages": ["en", "fr"],
                "tags": ["female"],
            },
            {"title": "no-id-entry"},  # skipped (no _id)
        ],
    }
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )

    voices = await provider.list_remote_voices()

    # The default narrator entry leads the trending listing.
    assert [v.id for v in voices] == [
        fish_module.FISH_NARRATOR_VOICE,
        "id-1",
        "id-2",
    ]
    assert voices[1].label == "Smash Announcer"
    assert voices[1].gender == "male"
    assert voices[2].gender == "female"
    assert voices[2].language == "en"
    # Trending (sort_by=score) when no query...
    call = fake.calls[0]
    assert call["params"]["sort_by"] == "score"
    assert call["headers"]["Authorization"] == "Bearer k"
    # ...title filter when searching (marketplace matches only, no
    # narrator prepend — a search wants results, not defaults).
    voices = await provider.list_remote_voices(query="mario")
    assert [v.id for v in voices] == ["id-1", "id-2"]
    search_call = fake.calls[1]
    assert search_call["params"].get("title") == "mario"
    assert "sort_by" not in search_call["params"]


@pytest.mark.asyncio
async def test_list_remote_voices_dedupes_narrator(monkeypatch):
    """A trending listing that already contains the narrator voice must
    not duplicate the prepended default entry."""
    provider = FishAudioTTSProvider(api_key="k")
    payload = {
        "items": [
            {
                "_id": fish_module.FISH_NARRATOR_VOICE,
                "title": "Sarah",
                "languages": ["en"],
                "tags": ["female"],
            }
        ]
    }
    _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )
    voices = await provider.list_remote_voices()
    assert [v.id for v in voices] == [fish_module.FISH_NARRATOR_VOICE]


@pytest.mark.asyncio
async def test_list_remote_voices_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    fake = _patch_fish_http(monkeypatch, FakeFishClient())
    assert await FishAudioTTSProvider().list_remote_voices() == []
    assert fake.calls == []


@pytest.mark.asyncio
async def test_list_tts_voices_unkeyed_returns_shortlist(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    fake = _patch_fish_http(monkeypatch, FakeFishClient())
    voices = await list_tts_voices("fish_audio")
    assert voices  # curated shortlist, no network call
    assert fake.calls == []


@pytest.mark.asyncio
async def test_list_tts_voices_keyed_lists_remote(monkeypatch):
    payload = {
        "items": [
            {
                "_id": "remote-1",
                "title": "Trending Voice",
                "languages": ["en"],
                "tags": [],
            }
        ]
    }
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )
    voices = await list_tts_voices("fish_audio", fish_api_key="vault")
    assert [v.id for v in voices] == [
        fish_module.FISH_NARRATOR_VOICE,
        "remote-1",
    ]  # default leads


@pytest.mark.asyncio
async def test_list_tts_voices_keyed_degrades_to_shortlist(monkeypatch):
    """A failing marketplace listing must not 502 the voice picker."""
    fake = FakeFishClient(get_resp=FakeResponse(status_code=500))
    fake.get_resp.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPError("boom")
    )
    _patch_fish_http(monkeypatch, fake)
    voices = await list_tts_voices("fish_audio", fish_api_key="vault")
    assert voices  # curated shortlist
    assert voices[0].id == fish_module.FISH_NARRATOR_VOICE


@pytest.mark.asyncio
async def test_list_tts_voices_search_keyed_hits_marketplace(monkeypatch):
    """An explicit search queries the live marketplace (page_size 50)."""
    payload = {
        "items": [
            {
                "_id": "mk-9",
                "title": "Mario",
                "languages": ["en"],
                "tags": ["male"],
            }
        ]
    }
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )
    voices = await list_tts_voices("fish_audio", fish_api_key="vault", search="mario")
    assert [v.id for v in voices] == ["mk-9"]
    call = fake.calls[0]
    assert call["params"]["title"] == "mario"
    assert call["params"]["page_size"] == 50
    assert "sort_by" not in call["params"]


@pytest.mark.asyncio
async def test_list_tts_voices_search_unkeyed_returns_empty(monkeypatch):
    """Unkeyed searches return no results (never the curated shortlist)."""
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    fake = _patch_fish_http(monkeypatch, FakeFishClient())
    assert await list_tts_voices("fish_audio", search="mario") == []
    assert fake.calls == []


@pytest.mark.asyncio
async def test_list_tts_voices_search_failure_returns_empty(monkeypatch):
    """A failing marketplace search yields [], not the shortlist."""
    fake = FakeFishClient(get_resp=FakeResponse(status_code=500))
    fake.get_resp.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPError("boom")
    )
    _patch_fish_http(monkeypatch, fake)
    voices = await list_tts_voices(
        "fish_audio", fish_api_key="vault", search="mario"
    )
    assert voices == []


# --- HTTP endpoints (integration) ----------------------------------------------------


def test_tts_endpoint_fish_synthesizes(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    lines = [
        _sse(
            {
                "audio_base64": _b64(b"fish-mp3"),
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
                "alignment": {
                    "segments": [{"text": "hi", "start": 0.0, "end": 0.4}]
                },
            }
        )
    ]
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(stream_resp=FakeStreamResponse(lines=lines))
    )

    resp = client.post(
        "/api/v1/tts",
        json={
            "text": "hi",
            "provider": "fish_audio",
            "voice": "abc123",
            "fish_api_key": "vault-key",
            "fish_model": "s2.1-pro-free",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "fish_audio"
    assert body["voice"] == "abc123"
    assert body["audio_url"].endswith(".mp3")
    # The vault key + model ride the upstream request.
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer vault-key"
    assert fake.calls[0]["headers"]["model"] == "s2.1-pro-free"


def test_tts_endpoint_fish_unconfigured_503(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    resp = client.post(
        "/api/v1/tts", json={"text": "hi", "provider": "fish_audio"}
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_tts_endpoint_fish_invalid_model_422():
    resp = client.post(
        "/api/v1/tts",
        json={"text": "hi", "provider": "fish_audio", "fish_model": "nope"},
    )
    assert resp.status_code == 422


def test_voices_endpoint_fish_shortlist_unkeyed(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    resp = client.get("/api/v1/voices", params={"provider": "fish_audio"})
    assert resp.status_code == 200
    voices = resp.json()
    assert voices  # curated shortlist
    assert voices[0]["id"] == fish_module.FISH_NARRATOR_VOICE  # narrator leads
    assert all("tags" in v for v in voices)


def test_voices_endpoint_fish_keyed_via_header(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    payload = {
        "items": [
            {
                "_id": "mk-1",
                "title": "Mario",
                "languages": ["en"],
                "tags": ["male"],
            }
        ]
    }
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )
    resp = client.get(
        "/api/v1/voices",
        params={"provider": "fish_audio"},
        headers={"X-Fish-API-Key": "header-key"},
    )
    assert resp.status_code == 200
    assert [v["id"] for v in resp.json()] == [
        fish_module.FISH_NARRATOR_VOICE,
        "mk-1",
    ]
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer header-key"


def test_voices_endpoint_fish_search_param(monkeypatch):
    """?search= rides the marketplace query as a title filter."""
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    payload = {
        "items": [
            {
                "_id": "smash-1",
                "title": "Smash Announcer",
                "languages": ["en"],
                "tags": ["male"],
            }
        ]
    }
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )
    resp = client.get(
        "/api/v1/voices",
        params={
            "provider": "fish_audio",
            "search": "smash",
            "fish_api_key": "vault",
        },
    )
    assert resp.status_code == 200
    assert [v["id"] for v in resp.json()] == ["smash-1"]
    assert fake.calls[0]["params"]["title"] == "smash"
    assert fake.calls[0]["params"]["page_size"] == 50


def test_voices_endpoint_fish_search_unkeyed_empty(monkeypatch):
    """Unkeyed search: 200 with no results (the picker shows the local
    filter matches instead of a bogus shortlist)."""
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    resp = client.get(
        "/api/v1/voices", params={"provider": "fish_audio", "search": "x"}
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_voices_endpoint_fish_header_wins_over_query(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    payload = {"items": []}
    fake = _patch_fish_http(
        monkeypatch, FakeFishClient(get_resp=FakeResponse(payload=payload))
    )
    resp = client.get(
        "/api/v1/voices",
        params={"provider": "fish_audio", "fish_api_key": "query-key"},
        headers={"X-Fish-API-Key": "header-key"},
    )
    assert resp.status_code == 200
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer header-key"


# --- Render pipeline pass-through -----------------------------------------------------


def test_render_request_fish_fields():
    from app.schemas.render_schema import RenderRequest

    request = RenderRequest(
        script=["line"],
        tts_provider="fish_audio",
        fish_api_key="vault",
        fish_model="s2.1-pro",
    )
    assert request.fish_api_key == "vault"
    assert request.fish_model == "s2.1-pro"
    with pytest.raises(ValueError):
        RenderRequest(
            script=["line"], tts_provider="fish_audio", fish_model="nope"
        )


def test_render_forwards_fish_credentials_to_provider(monkeypatch):
    """The render job builds its Fish provider with the client credentials."""
    from app.providers.tts import registry as tts_registry_module
    from app.schemas.render_schema import RenderRequest, StockClipRef
    from app.services import jobs as jobs_service
    from app.services.rendering import renderer

    captured: dict = {}
    original = tts_registry_module.get_tts_provider

    def spy(name, voice=None, **kwargs):
        captured.update(name=name, voice=voice, **kwargs)
        return original(name, voice=voice)

    monkeypatch.setattr(tts_registry_module, "get_tts_provider", spy)

    async def _stop(provider, text):
        raise RuntimeError("stop the job right after the provider is built")

    monkeypatch.setattr(renderer, "_synthesize_with_retry", _stop)

    request = RenderRequest(
        script=["line"],
        tts_provider="fish_audio",
        tts_voice="abc123",
        fish_api_key="vault-key",
        fish_model="s2.1-pro-free",
        # A stock-clip background skips gameplay asset resolution; the
        # downloads only start after TTS, which we abort on purpose.
        stock_clips=[
            StockClipRef(
                provider="pexels", id="1", url="https://x/1.mp4", duration_s=5.0
            )
        ],
    )
    job = jobs_service.job_store.create()
    asyncio.run(renderer.run_render_job(job.job_id, request))
    assert captured["name"] == "fish_audio"
    assert captured["voice"] == "abc123"
    assert captured["fish_api_key"] == "vault-key"
    assert captured["fish_model"] == "s2.1-pro-free"
    assert jobs_service.job_store.get(job.job_id).status.value == "failed"


# --- Health capability flag ------------------------------------------------------------


def test_health_reports_fish_capability(monkeypatch):
    monkeypatch.setattr(settings, "FISH_API_KEY", "some-key")
    caps = client.get("/health").json()["capabilities"]
    assert caps["tts_fish"] is True
    monkeypatch.setattr(settings, "FISH_API_KEY", "")
    caps = client.get("/health").json()["capabilities"]
    assert caps["tts_fish"] is False
