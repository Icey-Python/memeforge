"""Memeforge server settings.

Environment-driven configuration (12-factor style). Values can be set via
a `.env` file in `server/` or real environment variables.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # server/
ASSETS_DIR = BASE_DIR / "assets"
GAMEPLAY_DIR = ASSETS_DIR / "gameplay"
SFX_DIR = ASSETS_DIR / "sfx"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = Path(os.getenv("MEMEFORGE_OUTPUT_DIR", BASE_DIR / "outputs"))

# --- App ------------------------------------------------------------------

APP_TITLE = "Memeforge API"
APP_DESCRIPTION = (
    "Reddit-style gaming meme video generator: LLM script generation, "
    "TTS voiceover, and vertical split-screen video rendering."
)
APP_VERSION = "0.1.0"
API_V1_PREFIX = "/api/v1"

# --- Defaults -------------------------------------------------------------

# Default LLM provider used when a request does not specify one.
# Options: "openai" (OpenAI-compatible endpoint), "ollama", "mock".
DEFAULT_LLM_PROVIDER = os.getenv("MEMEFORGE_LLM_PROVIDER", "mock")

# OpenAI-compatible endpoint (works with OpenAI, LM Studio, vLLM, OpenRouter...)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Local Ollama endpoint
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# Default TTS provider: "edge" (free, via edge-tts), "azure", "elevenlabs".
DEFAULT_TTS_PROVIDER = os.getenv("MEMEFORGE_TTS_PROVIDER", "edge")
DEFAULT_EDGE_VOICE = os.getenv("MEMEFORGE_EDGE_VOICE", "en-US-ChristopherNeural")

# Azure Speech (paid tier; edge-tts uses the same neural voices for free)
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_DEFAULT_VOICE = os.getenv(
    "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
)

# --- Rendering ------------------------------------------------------------

# Vertical short format: top Reddit card, bottom gameplay loop.
VIDEO_WIDTH = int(os.getenv("MEMEFORGE_VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(os.getenv("MEMEFORGE_VIDEO_HEIGHT", "1920"))
VIDEO_FPS = int(os.getenv("MEMEFORGE_VIDEO_FPS", "30"))

# Path to the ffmpeg binary; falls back to whatever is on PATH.
FFMPEG_BIN = os.getenv("MEMEFORGE_FFMPEG", "ffmpeg")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging ---------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("memeforge")
