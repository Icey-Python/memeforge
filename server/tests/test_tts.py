"""TTS provider tests: registry wiring + TikTok payload handling (offline)."""

import base64

import pytest
from app.providers.tts.registry import _REGISTRY, get_tts_provider
from app.providers.tts.tiktok import TikTokTTSProvider, chunk_text


def test_registry_includes_tiktok():
    assert "tiktok" in _REGISTRY
    provider = get_tts_provider("tiktok")
    assert isinstance(provider, TikTokTTSProvider)
    assert provider.voice == "en_us_002"  # Jessie default
    assert provider.is_configured() is True  # free, keyless


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
