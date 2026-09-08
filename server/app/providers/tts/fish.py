"""Fish Audio TTS provider (fish.audio premium tier).

Marketplace voices (voice "models" addressed by `reference_id`), 83
languages, and word-level alignment timestamps. Requires FISH_API_KEY
(Bearer); client vault keys take priority over the server .env.

Primary path: POST /v1/tts/stream/with-timestamp — an SSE stream that
yields base64 audio chunks plus cumulative per-chunk word `alignment`
snapshots, mapped onto `SynthesizedAudio.word_timings` (with the chunk
offsets applied) for frame-accurate kinetic captions. Falls back to the
plain POST /v1/tts batch endpoint (binary audio, no timings) when the
streaming endpoint is unavailable.

Concurrency: Fish's free tier caps simultaneous requests at 5 (15/50 at
higher prepaid tiers). A process-global semaphore (FISH_CONCURRENCY)
keeps overlapping background render jobs from self-throttling.

Docs: https://docs.fish.audio — OpenAPI: https://api.fish.audio/openapi.json
"""

import asyncio
import base64
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from app.core import settings
from app.providers.tts.base import (
    BaseTTSProvider,
    SynthesizedAudio,
    Voice,
    WordTiming,
    strip_emotion_tags,
)

# Supported TTS models (sent as the `model` header on every request).
# s2.1-pro is the recommended production model; s2.1-pro-free is the
# same model on the zero-cost trial tier (no TTFA/DPA guarantees).
MODELS = ("s2.1-pro", "s2.1-pro-free", "s2-pro", "s1")
DEFAULT_MODEL = "s2.1-pro"

# Official Fish narrator voice (marketplace model "Sarah"). Fish Audio
# picks a RANDOM synthetic speaker for every request that omits
# `reference_id`, which breaks voice consistency across the lines of a
# render — so an empty/unconfigured voice resolves to this stable id
# instead (FISH_VOICE_ID in the server .env overrides it).
FISH_NARRATOR_VOICE = "933563129e564b19a115bedd57b7406a"

# Curated shortlist of trending marketplace voices (offline fallback for
# the voice picker; live listing via GET /model once a key is set). The
# leading entry is the official narrator every unconfigured voice falls
# back to (a real marketplace id, never the empty built-in default).
_VOICE_SHORTLIST: List[Voice] = [
    Voice(
        id=FISH_NARRATOR_VOICE,
        label="Sarah (default narrator)",
        language="en",
        gender="female",
        tags=["narration", "conversational"],
    ),
    Voice(
        id="90e65eaaf50e4470b8e6d43ee6afd7d5",
        label="Smash Bros Announcer",
        language="en",
        gender="male",
        tags=["meme", "character-voice"],
    ),
    Voice(
        id="d13f84b987ad4f22b56d2b47f4eb838e",
        label="Mortal Kombat",
        language="en",
        gender="male",
        tags=["meme", "deep"],
    ),
    Voice(
        id="802e3bc2b27e49c2995d23ef70e6ac89",
        label="Energetic Male",
        language="en",
        gender="male",
        tags=["meme", "energetic"],
    ),
    Voice(
        id="98655a12fa944e26b274c535e5e03842",
        label="E-girl",
        language="en",
        gender="female",
        tags=["conversational"],
    ),
    Voice(
        id="d8a1340984ee4b63ad1ffae27a6a4339",
        label="ELITE",
        language="en",
        gender="male",
        tags=["narration", "confident"],
    ),
    Voice(
        id="536d3a5e000945adb7038665781a4aca",
        label="Ethan",
        language="en",
        gender="male",
        tags=["narration"],
    ),
    Voice(
        id="bf322df2096a46f18c579d0baa36f41d",
        label="Adrian",
        language="en",
        gender="male",
        tags=["narration", "deep"],
    ),
    Voice(
        id="35a41c4c9e754e49a124a4bab5aa47e6",
        label="Energetic Crowd",
        language="en",
        gender="unknown",
        tags=["meme"],
    ),
]

_HTTP_TIMEOUT_S = 120.0
# Streaming endpoint statuses that mean "SSE not available here" — the
# provider degrades to the batch endpoint instead of failing.
_STREAM_UNAVAILABLE_STATUSES = {404, 405, 501}
# Actionable hints for the statuses a misconfigured deployment hits.
_STATUS_HINTS = {
    401: "invalid API key",
    402: "out of Fish Audio credits",
    403: "invalid API key",
    429: "Fish Audio concurrency limit reached (see FISH_CONCURRENCY)",
}

_RATE_RE = re.compile(r"^([+-]\d+(?:\.\d+)?)%$")

_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_loop_id: Optional[int] = None


def _fish_semaphore() -> asyncio.Semaphore:
    """Process-global request guard sized to the Fish concurrency tier.

    Re-created when the running event loop changes (each pytest-asyncio
    run gets a fresh loop; the long-lived server process keeps one).
    """
    global _semaphore, _semaphore_loop_id
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    if _semaphore is None or (
        loop_id is not None and loop_id != _semaphore_loop_id
    ):
        _semaphore = asyncio.Semaphore(max(1, settings.FISH_CONCURRENCY))
        _semaphore_loop_id = loop_id
    return _semaphore


def _rate_to_speed(rate: str) -> Optional[float]:
    """Map an edge-tts style rate ('+10%', '-5%') onto a Fish prosody
    speed multiplier (0.5-2.0). Neutral/invalid rates -> None (omit)."""
    match = _RATE_RE.match((rate or "").strip())
    if not match:
        return None
    pct = float(match.group(1))
    if pct == 0:
        return None
    return max(0.5, min(2.0, 1.0 + pct / 100.0))


def _parse_sse_data_line(line: str) -> Optional[dict]:
    """Parse one SSE `data:` line into a JSON event (None otherwise)."""
    if not line or not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        event = json.loads(payload)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def _assemble_sse_stream(
    events: Iterable[dict],
) -> Tuple[bytes, List[WordTiming]]:
    """Reconstruct audio + a global word timeline from SSE events.

    SSE contract (POST /v1/tts/stream/with-timestamp):
    - `audio_base64` chunks concatenate in arrival order.
    - `alignment` is a *cumulative* snapshot per `chunk_seq`: a later
      snapshot for the same chunk replaces the earlier one (never append).
    - `chunk_audio_offset_sec` is the chunk's absolute offset within the
      full audio; adding it to each segment's local start/end yields
      global word timestamps (the WordTiming contract).
    """
    audio = bytearray()
    snapshots: Dict[int, Dict[str, Any]] = {}
    for event in events:
        try:
            chunk_seq = int(event.get("chunk_seq") or 0)
        except (TypeError, ValueError):
            chunk_seq = 0
        b64 = event.get("audio_base64")
        if b64:
            try:
                audio.extend(base64.b64decode(b64))
            except (ValueError, TypeError):
                pass  # skip malformed audio chunks
        alignment = event.get("alignment")
        segments = (alignment or {}).get("segments")
        if segments:
            snapshots[chunk_seq] = {
                "offset": float(event.get("chunk_audio_offset_sec") or 0.0),
                "segments": segments,
            }
    timings: List[WordTiming] = []
    for chunk_seq in sorted(snapshots):
        snapshot = snapshots[chunk_seq]
        offset = snapshot["offset"]
        for seg in snapshot["segments"]:
            text = str((seg or {}).get("text", "")).strip()
            if not re.search(r"\w", text):
                continue  # punctuation-only segment (mirrors edge-tts)
            try:
                start = float(seg["start"]) + offset
                end = float(seg["end"]) + offset
            except (KeyError, TypeError, ValueError):
                continue
            if end > start >= 0.0:
                timings.append(WordTiming(text=text, start=start, end=end))
    return bytes(audio), timings


def _model_entity_to_voice(model: dict) -> Optional[Voice]:
    """Map a Fish marketplace ModelEntity onto the studio Voice shape."""
    voice_id = str(model.get("_id") or "").strip()
    if not voice_id:
        return None
    tags = [str(t) for t in (model.get("tags") or []) if str(t).strip()]
    gender = "unknown"
    for candidate in ("female", "male"):
        if candidate in tags:
            gender = candidate
            break
    languages = [str(l) for l in (model.get("languages") or []) if str(l).strip()]
    return Voice(
        id=voice_id,
        label=str(model.get("title") or voice_id).strip(),
        language=languages[0] if languages else "en",
        gender=gender,
        tags=tags or ["fish"],
    )


def _http_error(status_code: int, body: bytes) -> RuntimeError:
    """Actionable error for a non-200 Fish response."""
    hint = _STATUS_HINTS.get(status_code)
    detail = ""
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            detail = str(payload.get("message") or payload.get("detail") or "")
    except ValueError:
        pass
    if not detail:
        detail = body[:300].decode("utf-8", "replace").strip()
    message = f"Fish Audio TTS failed (HTTP {status_code})"
    if detail:
        message += f": {detail}"
    if hint:
        message += f" ({hint})"
    return RuntimeError(message)


class FishAudioTTSProvider(BaseTTSProvider):
    name = "fish_audio"

    def __init__(
        self,
        voice: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        # An empty/unconfigured voice resolves to the official narrator:
        # omitting reference_id would make Fish pick a random synthetic
        # speaker on every request (a different voice per script line).
        voice = (
            voice or settings.FISH_DEFAULT_VOICE or FISH_NARRATOR_VOICE
        ).strip()
        super().__init__(voice or FISH_NARRATOR_VOICE)
        # Client-supplied credentials (studio key vault) take priority
        # over the server .env default.
        self.api_key = (api_key or settings.FISH_API_KEY or "").strip()
        model = (model or settings.FISH_DEFAULT_MODEL or DEFAULT_MODEL).strip()
        if model not in MODELS:
            raise ValueError(
                f"Unknown Fish Audio model '{model}'. Available: {', '.join(MODELS)}"
            )
        self.model = model
        self.api_base = settings.FISH_API_BASE.rstrip("/")
        self.latency = settings.FISH_LATENCY.strip() or "normal"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self, accept: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "model": self.model,
        }
        if accept:
            headers["Accept"] = accept
        return headers

    def _build_payload(self, text: str, rate: str) -> Dict[str, Any]:
        # s2 models read bracketed delivery tags ([laugh], [whisper], ...)
        # natively as sound expressions, so they ride the text untouched.
        # The legacy s1 model would speak them literally: strip them.
        if not self.model.startswith("s2"):
            text = strip_emotion_tags(text) or text
        payload: Dict[str, Any] = {
            "text": text,
            "format": "mp3",
            "mp3_bitrate": 128,
            "latency": self.latency,
        }
        if self.voice:
            payload["reference_id"] = self.voice
        speed = _rate_to_speed(rate)
        if speed is not None:
            payload["prosody"] = {"speed": speed}
        return payload

    async def synthesize(
        self, text: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> SynthesizedAudio:
        """Synthesize one line; `pitch` is accepted but ignored (Fish
        exposes speed/volume, not pitch)."""
        if not self.is_configured():
            raise RuntimeError("Fish Audio TTS requires FISH_API_KEY")
        if not text or not text.strip():
            raise ValueError("empty text")
        # Primary: SSE stream (audio + cumulative word alignments).
        audio = await self._synthesize_stream(text, rate)
        if audio is not None:
            return audio
        # Fallback: batch endpoint (binary audio, no word timings).
        return await self._synthesize_batch(text, rate)

    async def _synthesize_stream(
        self, text: str, rate: str
    ) -> Optional[SynthesizedAudio]:
        """SSE timestamp path; None means "streaming unavailable" (the
        caller falls back to the batch endpoint)."""
        url = f"{self.api_base}/v1/tts/stream/with-timestamp"
        events: List[dict] = []
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            # Hold the semaphore for the whole stream: Fish counts the
            # request as active until the last chunk arrives.
            async with _fish_semaphore():
                async with client.stream(
                    "POST",
                    url,
                    json=self._build_payload(text, rate),
                    headers=self._headers(accept="text/event-stream"),
                ) as resp:
                    if resp.status_code in _STREAM_UNAVAILABLE_STATUSES:
                        return None
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise _http_error(resp.status_code, body)
                    async for line in resp.aiter_lines():
                        event = _parse_sse_data_line(line)
                        if event is not None:
                            events.append(event)
        audio_bytes, word_timings = _assemble_sse_stream(events)
        if not audio_bytes:
            return None  # stream produced no audio -> batch fallback
        return SynthesizedAudio(
            audio_bytes=audio_bytes,
            format="mp3",
            voice=self.voice,
            provider=self.name,
            word_timings=word_timings or None,
        )

    async def _synthesize_batch(self, text: str, rate: str) -> SynthesizedAudio:
        """Plain POST /v1/tts: chunked binary audio, no word timings."""
        url = f"{self.api_base}/v1/tts"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            async with _fish_semaphore():
                resp = await client.post(
                    url,
                    json=self._build_payload(text, rate),
                    headers=self._headers(accept="audio/mpeg"),
                )
        if resp.status_code != 200:
            raise _http_error(resp.status_code, resp.content)
        if not resp.content:
            raise RuntimeError("Fish Audio TTS returned no audio")
        return SynthesizedAudio(
            audio_bytes=resp.content,
            format="mp3",
            voice=self.voice,
            provider=self.name,
        )

    async def list_remote_voices(
        self, query: str = "", page_size: int = 20
    ) -> List[Voice]:
        """Search the Fish Audio voice marketplace (GET /model).

        Trending voices (sort_by=score) when `query` is empty — led by
        the default narrator — or title-matched marketplace results
        otherwise (no narrator prepend: a search wants matches only).
        """
        if not self.is_configured():
            return []
        params: Dict[str, Any] = {"page_size": page_size, "page_number": 1}
        term = query.strip()
        if term:
            params["title"] = term
        else:
            params["sort_by"] = "score"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.api_base}/model",
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        voices: List[Voice] = []
        if not term:
            voices.append(_VOICE_SHORTLIST[0])  # default narrator leads
        seen = {v.id for v in voices}
        for item in data.get("items", []):
            if isinstance(item, dict):
                voice = _model_entity_to_voice(item)
                if voice is not None and voice.id not in seen:
                    seen.add(voice.id)
                    voices.append(voice)
        return voices

    def list_voices(self) -> List[Voice]:
        return _VOICE_SHORTLIST
