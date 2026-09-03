"""Pydantic schemas for the memeforge API."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.providers.llm.base import DiscoveredModel


# --- Shared enums ---------------------------------------------------------


class LLMProvider(str, Enum):
    openai = "openai"  # any OpenAI-compatible endpoint
    ollama = "ollama"  # local models via Ollama
    mock = "mock"  # deterministic stub, no network


class TTSProvider(str, Enum):
    edge = "edge"  # free (edge-tts, Azure neural voices)
    meme_classic = "meme_classic"  # free (Brian & the iconic meme voices)
    tiktok = "tiktok"  # free (classic TikTok voices; auto-fallback when down)
    google = "google"  # free (Google Translate TTS reliability fallback)
    azure = "azure"  # Azure Speech (paid tier)
    elevenlabs = "elevenlabs"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class CardStyle(str, Enum):
    """Top card overlay style for the rendered video."""

    hook = "hook"  # bold hook headline card
    quote = "quote"  # quote card with decorative quote marks
    none = "none"  # clean full video without card


# --- Script generation ----------------------------------------------------


class ScriptGenerateRequest(BaseModel):
    topic: str = Field(..., description="Video topic, e.g. 'elden ring boss fights'")
    provider: LLMProvider = Field(
        default=LLMProvider.mock, description="LLM connector to use"
    )
    model: Optional[str] = Field(
        default=None, description="Model name override (provider-specific)"
    )
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "Provider base URL override, e.g. http://localhost:11434 for "
            "Ollama (falls back to the server .env default when blank)"
        ),
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key override (OpenAI-compatible endpoints)",
    )
    tone: str = Field(
        default="casual-commenter", description="Voice/tone of the script"
    )
    duration_target: int = Field(
        default=60,
        ge=10,
        le=300,
        description=(
            "Target spoken length in seconds (30/60/90 are the studio "
            "presets). Drives the word-count target: ~2.2-2.5 words/sec "
            "of speech, so 60s ≈ 130-150 words — the sweet spot for "
            "YouTube Shorts, TikTok, and Reels"
        ),
    )
    max_lines: Optional[int] = Field(
        default=None,
        ge=1,
        le=40,
        description=(
            "Line cap; defaults to a duration-derived pacing (~4s of "
            "speech per line) when omitted"
        ),
    )


class ScriptLine(BaseModel):
    index: int
    text: str
    # words per caption frame; the compositor chunks kinetic captions 1-2 words
    is_punchline: bool = False


class ScriptResponse(BaseModel):
    topic: str
    title: str
    provider: str
    model: Optional[str] = None
    lines: List[ScriptLine]
    generated_at: datetime


# --- Live model discovery ---------------------------------------------------


class ModelDiscoveryRequest(BaseModel):
    provider: LLMProvider = Field(
        ..., description="LLM connector whose endpoint should be queried"
    )
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "Provider base URL override, e.g. http://localhost:11434 for "
            "Ollama (falls back to the server .env default when blank)"
        ),
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key override (OpenAI-compatible endpoints)",
    )


class ModelDiscoveryResponse(BaseModel):
    provider: str
    base_url: Optional[str] = None
    reachable: bool
    error: Optional[str] = None
    models: List[DiscoveredModel] = []


# --- TTS -------------------------------------------------------------------


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    provider: TTSProvider = Field(default=TTSProvider.edge)
    voice: Optional[str] = Field(
        default=None, description="Voice name/ID; defaults per provider"
    )
    rate: str = Field(default="+0%", description="Speech rate adjustment, e.g. '+10%'")
    pitch: str = Field(default="+0Hz", description="Pitch adjustment, e.g. '-5Hz'")
    api_key: Optional[str] = Field(
        default=None,
        description=(
            "Per-request API key override for keyed providers "
            "(ElevenLabs, Azure) — wins over the server .env"
        ),
    )
    region: Optional[str] = Field(
        default=None,
        description="Azure Speech region override, e.g. 'eastus'",
    )


class TTSResponse(BaseModel):
    provider: str
    voice: str
    audio_url: str
    duration_hint_ms: Optional[int] = None


# --- Rendering -------------------------------------------------------------


class StockClipRef(BaseModel):
    """One picked stock clip (Pexels / Pixabay) for the render background."""

    provider: str = Field(..., description="Stock provider: 'pexels' or 'pixabay'")
    id: str = Field(..., description="Clip id at the provider")
    url: str = Field(..., description="Direct download URL of the clip")
    duration_s: float = Field(..., ge=0.1, description="Clip duration in seconds")
    label: str = Field(default="", description="Display title (thumbnail tooltip)")


class RenderRequest(BaseModel):
    topic: str = ""
    title: str = Field(
        default="",
        description="Headline for the top card (hook/quote styles only)",
    )
    script: List[str] = Field(..., min_length=1)
    tts_provider: TTSProvider = Field(default=TTSProvider.edge)
    tts_voice: Optional[str] = None
    gameplay_id: Optional[str] = Field(
        default=None,
        description=(
            "Background loop id from /api/v1/render/gameplays "
            "(preset clips; required when stock_clips is empty)"
        ),
    )
    stock_clips: List[StockClipRef] = Field(
        default=[],
        description=(
            "Stock clips (Pexels / Pixabay) stitched into the background; "
            "when set, overrides gameplay_id. Multiple clips are "
            "concatenated with cuts to cover the voiceover duration."
        ),
    )
    card_style: CardStyle = Field(
        default=CardStyle.hook,
        description=(
            "Top card overlay: 'hook' (bold headline), 'quote' (quote "
            "card), or 'none' (clean full video without card)"
        ),
    )
    caption_style: str = Field(
        default="kinetic-stroke", description="Caption rendering style"
    )
    sfx_on_punchlines: bool = Field(default=True)
    tts_api_key: Optional[str] = Field(
        default=None,
        description=(
            "Per-request API key for keyed TTS providers (ElevenLabs, "
            "Azure) — wins over the server .env so renders work without "
            "any backend configuration"
        ),
    )
    tts_region: Optional[str] = Field(
        default=None,
        description="Azure Speech region override, e.g. 'eastus'",
    )


class RenderJob(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RenderAccepted(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str


# --- Catalogs ---------------------------------------------------------------


class GameplayClip(BaseModel):
    id: str
    label: str
    game: str
    description: str
    source: Optional[str] = None  # resolved path/URL of the loop
    available: bool = False


class VoiceOption(BaseModel):
    id: str
    label: str
    language: str
    gender: str
    tags: List[str] = []


# --- Stock video search (Pexels / Pixabay) -----------------------------------


class StockVideoResult(BaseModel):
    """One searchable vertical stock clip (normalized across providers)."""

    id: str
    provider: str
    title: str
    duration_s: float
    width: int
    height: int
    thumbnail_url: str = ""
    video_url: str
    author: str = ""
    is_demo: bool = False


class StockProviderInfo(BaseModel):
    id: str
    label: str
    keyed: bool


class StockSearchResponse(BaseModel):
    query: str
    videos: List[StockVideoResult]
    providers: List[StockProviderInfo]
    notice: Optional[str] = None


class KeywordExtractRequest(BaseModel):
    script: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        description="The full script text (lines joined by newlines)",
    )
    provider: LLMProvider = Field(
        default=LLMProvider.mock,
        description="LLM connector used for extraction (mock → heuristic)",
    )
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class KeywordExtractResponse(BaseModel):
    queries: List[str] = Field(
        ..., description="3-5 visual stock-video search queries"
    )
    source: str = Field(
        ..., description="'llm' when the model produced the queries, else 'heuristic'"
    )
