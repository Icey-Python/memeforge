"""TTS provider tests: registry wiring, payload handling, fallbacks (offline)."""

import base64

import pytest
from app.core import settings
from app.providers.tts.base import (
    SynthesizedAudio,
    chunk_text,
    split_emotion_segments,
    strip_emotion_tags,
)
from app.providers.tts.edge import EdgeTTSProvider
from app.providers.tts.google import GoogleTTSProvider
from app.providers.tts.meme_classic import MemeClassicTTSProvider
from app.providers.tts.registry import _REGISTRY, get_tts_provider
from app.providers.tts.tiktok import TikTokTTSProvider


# --- Emotion / delivery tags --------------------------------------------------


def test_strip_emotion_tags():
    assert strip_emotion_tags("[whisper] hello world") == "hello world"
    assert strip_emotion_tags("this is [excited] insane") == "this is insane"
    assert strip_emotion_tags("multi [laugh] tag [angry] case") == "multi tag case"
    assert strip_emotion_tags("[GASP] shouty caps") == "shouty caps"  # any case
    assert strip_emotion_tags("[ sigh ] spaced") == "spaced"  # inner spaces
    # Non-emotion brackets survive untouched.
    assert strip_emotion_tags("butter [sic] toast") == "butter [sic] toast"
    assert strip_emotion_tags("[Intro] music") == "[Intro] music"
    # Degenerate inputs.
    assert strip_emotion_tags("[laugh]") == ""
    assert strip_emotion_tags("") == ""
    assert strip_emotion_tags("plain text") == "plain text"


def test_split_emotion_segments():
    assert split_emotion_segments("hey [whisper] listen [angry] now") == [
        (None, "hey "),
        ("whisper", " listen "),
        ("angry", " now"),
    ]
    assert split_emotion_segments("plain text") == [(None, "plain text")]
    assert split_emotion_segments("[laugh] only tagged") == [
        ("laugh", " only tagged")
    ]


def test_fish_passes_emotion_tags_on_s2_models():
    """Fish s2 models read bracketed tags natively: they ride the text."""
    from app.providers.tts.fish import FishAudioTTSProvider

    for model in ("s2.1-pro", "s2.1-pro-free", "s2-pro"):
        provider = FishAudioTTSProvider(api_key="k", model=model)
        payload = provider._build_payload("you [laugh] did not", "+0%")
        assert payload["text"] == "you [laugh] did not"


def test_fish_strips_emotion_tags_on_s1():
    """The legacy s1 model would speak tags literally: strip them."""
    from app.providers.tts.fish import FishAudioTTSProvider

    provider = FishAudioTTSProvider(api_key="k", model="s1")
    payload = provider._build_payload("you [laugh] did not", "+0%")
    assert payload["text"] == "you did not"


def test_azure_build_ssml_converts_emotion_tags():
    """Delivery tags become mstts:express-as style runs."""
    from app.providers.tts.azure import build_ssml

    ssml = build_ssml(
        "and then [whisper] he said [angry] no", "en-US-GuyNeural",
        "+0%", "+0Hz",
    )
    assert 'xmlns:mstts="https://www.w3.org/2001/mstts"' in ssml
    assert '<mstts:express-as style="whispering">he said</mstts:express-as>' in ssml
    assert '<mstts:express-as style="angry">no</mstts:express-as>' in ssml
    assert "and then" in ssml
    # Every supported tag maps to a documented style.
    for tag, style in [
        ("whisper", "whispering"), ("laugh", "cheerful"), ("gasp", "fearful"),
        ("excited", "excited"), ("sigh", "disgruntled"), ("angry", "angry"),
    ]:
        ssml = build_ssml(f"[{tag}] boom", "v", "+0%", "+0Hz")
        assert f'<mstts:express-as style="{style}">boom</mstts:express-as>' in ssml


def test_azure_build_ssml_plain_text_has_no_express_as():
    from app.providers.tts.azure import build_ssml

    ssml = build_ssml("plain line", "en-US-GuyNeural", "+10%", "+0Hz")
    assert "express-as" not in ssml
    assert '<prosody rate="+10%" pitch="+0Hz">' in ssml


def test_azure_build_ssml_escapes_xml():
    from app.providers.tts.azure import build_ssml

    ssml = build_ssml("fish & <chips>", "v", "+0%", "+0Hz")
    assert "fish &amp; &lt;chips&gt;" in ssml


@pytest.mark.asyncio
async def test_edge_strips_emotion_tags(monkeypatch):
    """Edge-TTS never receives bracketed tags (it would speak them)."""
    import edge_tts

    captured = {}

    class CapturingCommunicate(_FakeEdgeCommunicate):
        def __init__(self, text: str, voice: str, **kwargs):
            captured["text"] = text
            super().__init__(text, voice, **kwargs)

    monkeypatch.setattr(edge_tts, "Communicate", CapturingCommunicate)
    await EdgeTTSProvider().synthesize("brace [whisper] yourself")
    assert captured["text"] == "brace yourself"


@pytest.mark.asyncio
async def test_tiktok_strips_emotion_tags(monkeypatch):
    captured = {}

    async def ok_chunk(self, text: str) -> bytes:
        captured["text"] = text
        return b"tiktok-mp3"

    monkeypatch.setattr(TikTokTTSProvider, "_synthesize_chunk", ok_chunk)
    await TikTokTTSProvider().synthesize("hello [laugh] world")
    assert captured["text"] == "hello world"


@pytest.mark.asyncio
async def test_meme_classic_strips_emotion_tags(monkeypatch):
    captured = {}

    async def ok_chunk(self, text: str) -> bytes:
        captured["text"] = text
        return b"brian-mp3"

    monkeypatch.setattr(MemeClassicTTSProvider, "_synthesize_chunk", ok_chunk)
    await MemeClassicTTSProvider().synthesize("brian [sigh] says hi")
    assert captured["text"] == "brian says hi"


@pytest.mark.asyncio
async def test_google_strips_emotion_tags(monkeypatch):
    captured = {}

    async def ok_chunk(self, text: str) -> bytes:
        captured["text"] = text
        return b"google-mp3"

    monkeypatch.setattr(GoogleTTSProvider, "_synthesize_chunk", ok_chunk)
    await GoogleTTSProvider().synthesize("hello [gasp] world")
    assert captured["text"] == "hello world"


@pytest.mark.asyncio
async def test_elevenlabs_strips_emotion_tags(monkeypatch):
    """ElevenLabs v2 has no bracketed tag support: strip before POST."""
    from app.providers.tts import elevenlabs as eleven_module

    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"eleven-mp3"

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
            captured["payload"] = json
            return FakeResponse()

    provider = eleven_module.ElevenLabsProvider(api_key="k")
    monkeypatch.setattr(eleven_module.httpx, "AsyncClient", FakeClient)
    audio = await provider.synthesize("hey [excited] listen")
    assert captured["payload"]["text"] == "hey listen"
    assert audio.audio_bytes == b"eleven-mp3"


def test_caption_timeline_strips_emotion_tags():
    """Burned-in captions show only spoken words, never the tags."""
    from app.services.rendering.captions import build_caption_timeline

    frames = build_caption_timeline(
        ["[whisper] brace yourself [laugh] gamers"], [2.0]
    )
    assert [f.words for f in frames] == ["BRACE YOURSELF", "GAMERS"]


def test_card_title_strips_emotion_tags():
    """The headline card falls back to the first line, tag-free."""
    from app.schemas.render_schema import RenderRequest
    from app.services.rendering.renderer import _card_title

    request = RenderRequest(script=["[gasp] the reveal", "punchline"])
    assert _card_title(request) == "the reveal"


# --- Registry ---------------------------------------------------------------


def test_registry_includes_all_providers():
    assert set(_REGISTRY) == {
        "edge",
        "meme_classic",
        "tiktok",
        "google",
        "fish_audio",
        "azure",
        "elevenlabs",
    }


def test_registry_includes_tiktok():
    provider = get_tts_provider("tiktok")
    assert isinstance(provider, TikTokTTSProvider)
    assert provider.voice == "en_us_002"  # Jessie default
    assert provider.is_configured() is True  # free, keyless


# --- Meme Classic (ttsmp3 / Polly voices) -----------------------------------


def test_registry_includes_meme_classic():
    provider = get_tts_provider("meme_classic")
    assert isinstance(provider, MemeClassicTTSProvider)
    assert provider.voice == "Brian"  # THE meme TTS voice
    assert provider.is_configured() is True  # free, keyless


def test_meme_classic_voice_catalog():
    voices = MemeClassicTTSProvider().list_voices()
    ids = {v.id for v in voices}
    assert {
        "Brian",  # iconic British male
        "Justin",  # kid/teen
        "Matthew",  # deep narrator
        "Kendra",
        "Salli",
        "Joey",
        "Ivy",
        "Joanna",
    } <= ids
    assert all("meme" in v.tags for v in voices)
    # Brian leads the catalog — the flagship meme voice.
    assert voices[0].id == "Brian"


def test_meme_classic_extract_mp3_url():
    # Success shape: absolute URL + MP3 basename.
    payload = {
        "Error": 0,
        "Speaker": "Brian",
        "URL": "https://ttsmp3.com/created_mp3/abc123.mp3",
        "MP3": "abc123.mp3",
        "success": 1,
    }
    assert (
        MemeClassicTTSProvider._extract_mp3_url(payload)
        == "https://ttsmp3.com/created_mp3/abc123.mp3"
    )
    # Basename-only shape resolves against the created_mp3 folder.
    assert MemeClassicTTSProvider._extract_mp3_url(
        {"Error": 0, "MP3": "xyz.mp3"}
    ) == "https://ttsmp3.com/created_mp3/xyz.mp3"

    # Error payloads raise instead of returning garbage.
    with pytest.raises(RuntimeError):
        MemeClassicTTSProvider._extract_mp3_url({"Error": 1})
    # Missing MP3 info raises.
    with pytest.raises(RuntimeError):
        MemeClassicTTSProvider._extract_mp3_url({"Error": 0})
    with pytest.raises(RuntimeError):
        MemeClassicTTSProvider._extract_mp3_url("not-a-dict")


# --- Google Translate TTS -----------------------------------------------------


def test_registry_includes_google():
    provider = get_tts_provider("google")
    assert isinstance(provider, GoogleTTSProvider)
    assert provider.voice == "en"  # US English default
    assert provider.is_configured() is True  # free, keyless


def test_google_voice_catalog():
    voices = GoogleTTSProvider().list_voices()
    ids = {v.id for v in voices}
    assert {"en", "en-GB", "en-AU", "en-IN"} <= ids  # tl language codes


def test_google_chunk_limit():
    # The translate_tts endpoint rejects requests over ~200 chars.
    assert chunk_text("hello world", limit=200) == ["hello world"]
    long = " ".join(["word"] * 200)  # 1000 chars -> multiple chunks
    chunks = chunk_text(long, limit=200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(chunks) == long


# --- TikTok: payload handling -------------------------------------------------


def test_tiktok_voice_catalog():
    voices = TikTokTTSProvider().list_voices()
    ids = {v.id for v in voices}
    assert {
        "en_us_002",  # Jessie
        "en_male_cody",  # Serious Male
        "en_male_narration",  # Narrator
        "en_us_ghostface",  # Ghostface
        "en_us_trickster",  # Trickster
    } <= ids
    assert all("meme" in v.tags for v in voices)


def test_tiktok_extract_audio():
    mp3 = b"\xff\xfbFakeMp3FrameData"
    payload = {"status_code": 0, "data": base64.b64encode(mp3).decode()}
    assert TikTokTTSProvider._extract_audio(payload) == mp3

    # Some mirrors return a list of base64 parts.
    payload = {"status_code": 0, "data": [base64.b64encode(mp3).decode()]}
    assert TikTokTTSProvider._extract_audio(payload) == mp3

    # Error statuses raise instead of returning garbage.
    with pytest.raises(RuntimeError):
        TikTokTTSProvider._extract_audio({"status_code": 5, "data": "x"})
    with pytest.raises(RuntimeError):
        TikTokTTSProvider._extract_audio({"status_code": 0, "data": ""})


def test_tiktok_chunk_text():
    assert chunk_text("hello world") == ["hello world"]
    assert chunk_text("") == []

    long = " ".join(["word"] * 200)  # 1000 chars → multiple chunks
    chunks = chunk_text(long)
    assert len(chunks) > 1
    assert all(len(c) <= 280 for c in chunks)
    assert " ".join(chunks) == long  # lossless on word boundaries


# --- TikTok: session cookie ----------------------------------------------------


def test_tiktok_session_id_cookie(monkeypatch):
    monkeypatch.setattr(settings, "TIKTOK_SESSION_ID", "sess-123")
    assert TikTokTTSProvider()._session_cookies() == {"sessionid": "sess-123"}

    monkeypatch.setattr(settings, "TIKTOK_SESSION_ID", "")
    assert TikTokTTSProvider()._session_cookies() is None

    # Whitespace-only values are treated as unset.
    monkeypatch.setattr(settings, "TIKTOK_SESSION_ID", "   ")
    assert TikTokTTSProvider()._session_cookies() is None


# --- TikTok: automatic fallback --------------------------------------------------


async def _brian_audio(self, text: str, rate: str = "+0%", pitch: str = "+0Hz"):
    return SynthesizedAudio(
        audio_bytes=b"brian-mp3-bytes",
        format="mp3",
        voice="Brian",
        provider="meme_classic",
    )


async def _edge_audio(self, text: str, rate: str = "+0%", pitch: str = "+0Hz"):
    return SynthesizedAudio(
        audio_bytes=b"edge-mp3-bytes",
        format="mp3",
        voice="en-US-ChristopherNeural",
        provider="edge",
    )


async def _boom(self, text: str):
    raise RuntimeError("all TikTok mirrors returned HTTP 404")


# --- Edge-TTS: word-boundary metadata ----------------------------------------


class _FakeEdgeCommunicate:
    """Stand-in for edge_tts.Communicate yielding audio + WordBoundaries."""

    def __init__(self, text: str, voice: str, **kwargs):
        self.kwargs = kwargs

    async def stream(self):
        for chunk in [
            {"type": "audio", "data": b"mp3-bytes-"},
            {
                "type": "WordBoundary",
                "offset": 1_000_000,  # 100ns ticks → 0.1s
                "duration": 2_000_000,  # → 0.2s
                "text": "brace",
            },
            {"type": "audio", "data": b"more-bytes"},
            {
                "type": "WordBoundary",
                "offset": 4_000_000,  # → 0.4s
                "duration": 3_000_000,  # → 0.3s
                "text": "yourself",  # word chars only
            },
            {
                "type": "WordBoundary",
                "offset": 8_000_000,
                "duration": 500_000,
                "text": ",",  # punctuation-only: dropped
            },
        ]:
            yield chunk


@pytest.mark.asyncio
async def test_edge_tts_collects_word_timings(monkeypatch):
    """WordBoundary events become exact second-based word timings."""
    import edge_tts

    monkeypatch.setattr(edge_tts, "Communicate", _FakeEdgeCommunicate)

    audio = await EdgeTTSProvider().synthesize("brace yourself")

    assert audio.audio_bytes == b"mp3-bytes-more-bytes"
    assert audio.word_timings is not None
    assert [(t.text, t.start, t.end) for t in audio.word_timings] == [
        ("brace", pytest.approx(0.1), pytest.approx(0.3)),
        ("yourself", pytest.approx(0.4), pytest.approx(0.7)),
    ]


@pytest.mark.asyncio
async def test_edge_tts_requests_word_boundaries(monkeypatch):
    """Synthesis asks the service for word-level boundary metadata."""
    import edge_tts

    captured = {}

    class CapturingCommunicate(_FakeEdgeCommunicate):
        def __init__(self, text, voice, **kwargs):
            captured.update(kwargs)
            super().__init__(text, voice, **kwargs)

    monkeypatch.setattr(edge_tts, "Communicate", CapturingCommunicate)
    await EdgeTTSProvider().synthesize("hello")
    assert captured.get("boundary") == "WordBoundary"


@pytest.mark.asyncio
async def test_edge_tts_word_timings_none_without_boundaries(monkeypatch):
    """No WordBoundary events (older edge-tts) -> timings stay None."""
    import edge_tts

    class AudioOnlyCommunicate:
        def __init__(self, text: str, voice: str, **kwargs):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"mp3"}

    monkeypatch.setattr(edge_tts, "Communicate", AudioOnlyCommunicate)
    audio = await EdgeTTSProvider().synthesize("hello")
    assert audio.word_timings is None


@pytest.mark.asyncio
async def test_tiktok_falls_back_to_edge(monkeypatch):
    """Broken TikTok endpoints degrade to edge-tts instead of failing."""
    monkeypatch.setattr(TikTokTTSProvider, "_synthesize_chunk", _boom)
    monkeypatch.setattr(EdgeTTSProvider, "synthesize", _edge_audio)

    audio = await TikTokTTSProvider().synthesize("hello world")
    assert audio.provider == "edge"
    assert audio.audio_bytes == b"edge-mp3-bytes"


@pytest.mark.asyncio
async def test_tiktok_falls_back_to_brian(monkeypatch):
    """If edge is also down, the iconic Brian voice keeps the render alive."""
    monkeypatch.setattr(TikTokTTSProvider, "_synthesize_chunk", _boom)

    async def edge_boom(self, text, rate="+0%", pitch="+0Hz"):
        raise RuntimeError("edge-tts is down")

    monkeypatch.setattr(EdgeTTSProvider, "synthesize", edge_boom)
    monkeypatch.setattr(MemeClassicTTSProvider, "synthesize", _brian_audio)

    audio = await TikTokTTSProvider().synthesize("hello world")
    assert audio.provider == "meme_classic"
    assert audio.voice == "Brian"
    assert audio.audio_bytes == b"brian-mp3-bytes"


@pytest.mark.asyncio
async def test_tiktok_raises_when_all_fallbacks_fail(monkeypatch):
    """Every engine down -> a clear error naming the original failure."""
    monkeypatch.setattr(TikTokTTSProvider, "_synthesize_chunk", _boom)

    async def also_boom(self, text, rate="+0%", pitch="+0Hz"):
        raise RuntimeError("down")

    monkeypatch.setattr(EdgeTTSProvider, "synthesize", also_boom)
    monkeypatch.setattr(MemeClassicTTSProvider, "synthesize", also_boom)

    with pytest.raises(RuntimeError, match="all TikTok mirrors returned HTTP 404"):
        await TikTokTTSProvider().synthesize("hello world")


@pytest.mark.asyncio
async def test_tiktok_no_fallback_on_success(monkeypatch):
    """A healthy TikTok response is returned as-is (provider stays tiktok)."""

    async def ok_chunk(self, text: str) -> bytes:
        # _synthesize_chunk returns already-decoded mp3 bytes.
        return b"tiktok-mp3"

    monkeypatch.setattr(TikTokTTSProvider, "_synthesize_chunk", ok_chunk)
    monkeypatch.setattr(
        EdgeTTSProvider, "synthesize", _edge_audio
    )  # must NOT be called

    audio = await TikTokTTSProvider().synthesize("hello world")
    assert audio.provider == "tiktok"
    assert audio.audio_bytes == b"tiktok-mp3"


@pytest.mark.asyncio
async def test_tiktok_empty_text_still_raises(monkeypatch):
    monkeypatch.setattr(TikTokTTSProvider, "_synthesize_chunk", _boom)
    with pytest.raises(ValueError, match="empty text"):
        await TikTokTTSProvider().synthesize("")
