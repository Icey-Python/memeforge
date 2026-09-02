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
    tiktok = "tiktok"  # free (classic TikTok meme voices)
    azure = "azure"  # Azure Speech (paid tier)
    elevenlabs = "elevenlabs"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


# --- Script generation ----------------------------------------------------


class ScriptGenerateRequest(BaseModel):
    topic: str = Field(..., description="Meme topic, e.g. 'elden ring boss fights'")
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
        default="reddit-commenter", description="Voice/tone of the script"
    )
    max_lines: int = Field(default=8, ge=1, le=40)


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


class TTSResponse(BaseModel):
    provider: str
    voice: str
    audio_url: str
    duration_hint_ms: Optional[int] = None


# --- Rendering -------------------------------------------------------------


class RenderRequest(BaseModel):
    topic: str = ""
    title: str = Field(default="", description="Headline for the Reddit-style card")
    script: List[str] = Field(..., min_length=1)
    tts_provider: TTSProvider = Field(default=TTSProvider.edge)
    tts_voice: Optional[str] = None
    gameplay_id: str = Field(..., description="Gameplay loop id from /api/v1/render/gameplays")
    caption_style: str = Field(
        default="kinetic-stroke", description="Caption rendering style"
    )
    sfx_on_punchlines: bool = Field(default=True)


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
