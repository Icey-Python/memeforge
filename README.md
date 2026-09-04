# memeforge

AI vertical video generator. Turn a topic — or your own pasted script —
into a vertical 1080×1920 short-form video: full-screen background
loop, an optional hook headline or quote card, kinetic captions, free
voiceover. Built for YouTube Shorts, TikTok, and Reels pacing.



https://github.com/user-attachments/assets/7e9c4c7c-b85a-4174-bae1-7a0295c6e780



https://github.com/user-attachments/assets/fa564d12-830d-41b2-98e5-09c7ea44e1a6



## Monorepo layout

| Path | What |
| --- | --- |
| `web/` | Next.js 16 App Router studio — React Flow canvas with modular nodes (Model Connector → Topic → Script → Voiceover → Preview, plus Gameplay), dark sleek UI |
| `server/` | FastAPI backend — LLM script generation (OpenAI-compatible / Ollama / mock), TTS (edge-tts free default, Meme Classic with Brian & the iconic meme voices, TikTok with auto-fallback, Google Translate, Azure, ElevenLabs), async ffmpeg render jobs |

## Quickstart

```bash
# 1. Backend (http://localhost:8000)
cd server
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload --port 8000

# 2. Frontend (http://localhost:3000)
cd web
pnpm install
cp .env.example .env
pnpm dev
```

Or run both at once: `./scripts/dev.sh`.

Zero-config demo: the default **Mock** LLM provider works offline, and
**edge-tts** needs no API key — the whole topic → script → voiceover →
render pipeline runs without any credentials. The **Meme Classic**
provider (Brian, Justin, Matthew — the iconic Twitch meme voices) and
**Google Translate TTS** are free and keyless too; the legacy **TikTok
meme voices** provider falls back to edge-tts / Brian automatically
when its unofficial endpoints reject anonymous calls.

### Background clips

Render requires a background loop. Drop `<id>.mp4` files into
`server/assets/gameplay/` (e.g. `minecraft-parkour.mp4`) — the studio's
Gameplay node flips to `CLIP READY` automatically. Long clips (5+ min)
get a random seek in-point per render so repeated renders surface fresh
footage. Optional punchline SFX goes in `server/assets/sfx/`.
`server/scripts/fetch-gameplay.sh` can pull public-domain clips.

## The studio pipeline

1. **Model Connector** — pick an LLM provider + model (live model discovery from
   Ollama / OpenAI-compatible endpoints; mock works offline)
2. **Topic / Prompt** — topic, tone, target duration (30/60/90s) → *Generate
   script*; or switch the Script node to **Custom** and paste your own script
3. **Script** — generated or pasted; every line editable, reorderable, and
   removable, with live word count + spoken-length estimate. The 60s default
   targets ~140 words (~2.3 words/sec), the sweet spot for Shorts/TikTok/Reels
4. **Voiceover / TTS** — provider + voice, free by default (Meme Classic
   Brian & friends and TikTok meme voices come with direct per-voice
   previews)
5. **Gameplay / Background** — pick a background clip with asset status
6. **Preview & Export** — readiness checklist, top-card style (hook / quote /
   clean), render → inline player

## API (v1)

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | liveness + ffmpeg/edge-tts capability probe |
| `GET /api/v1/models` | available LLM providers |
| `POST /api/v1/models/discover` | live model list for a provider (Ollama `/api/tags`, OpenAI-compatible `/v1/models`) |
| `POST /api/v1/generate-script` | topic + duration target → short-form script (mock/openai-compatible/ollama) |
| `GET /api/v1/voices?provider=edge` | TTS voice catalog (`edge\|meme_classic\|tiktok\|google\|azure\|elevenlabs`) |
| `POST /api/v1/tts` | synthesize one line → audio url |
| `GET /api/v1/render/gameplays` | background clip catalog + availability |
| `POST /api/v1/render` | queue a render job (async; `card_style`: hook/quote/none) |
| `GET /api/v1/render/{job_id}` | poll job progress → `video_url` |

Interactive docs: http://localhost:8000/docs.

## Architecture notes

- **Render pipeline** — per-line TTS → duration probing (ffprobe) → caption
  timeline → Pillow caption PNGs + optional headline/quote card → ffmpeg
  full-screen `overlay` compositor (background fills the whole 1080×1920
  frame; the card floats upper-center and fades after the hook; long clips
  start at a random seek) → H.264. Captions deliberately avoid ffmpeg's
  optional `drawtext` filter (absent from Homebrew builds) — works on any
  ffmpeg.
- **Duration pacing** — script generation takes a `duration_target`
  (default 60s). Word budgets use ~2.2–2.5 words/sec of speech (60s ≈
  130–150 words) and line counts ~4s of speech per line.
- **Resilience** — per-line TTS timeout + retries, ffmpeg/ffprobe subprocess
  timeouts, in-memory job store with progress polling.
- **CORS** — any `localhost`/`127.0.0.1` origin allowed in dev; set
  `MEMEFORGE_CORS_ORIGINS` for production.
