# memeforge

AI-powered Reddit-style meme video generator. Turn a topic into a
vertical 1080×1920 "gameplay split-screen" short — r/gaming card on top,
satisfying gameplay loop below, kinetic captions, free neural voiceover.

```
┌─────────────────────────┐
│   r/gaming meme card    │  ← Pillow-rendered Reddit post (title, upvotes)
├─────────────────────────┤
│   KINETIC CAPTIONS      │  ← 1–2 words/frame, heavy stroke, punchline pop
│                         │
│   gameplay loop         │  ← minecraft parkour, subway surfers, GTA stunts…
└─────────────────────────┘
     + edge-tts voiceover, optional punchline SFX 💥
```

## Monorepo layout

| Path | What |
| --- | --- |
| `web/` | Next.js 16 App Router studio — React Flow canvas with modular nodes (Model Connector → Topic → Script → Voiceover → Preview, plus Gameplay), dark sleek UI |
| `server/` | FastAPI backend — LLM script generation (OpenAI-compatible / Ollama / mock), TTS (edge-tts free default, Azure, ElevenLabs), async ffmpeg render jobs |

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
render pipeline runs without any credentials.

### Gameplay clips

Render requires a gameplay loop. Drop `<id>.mp4` files into
`server/assets/gameplay/` (e.g. `minecraft-parkour.mp4`) — the studio's
Gameplay node flips to `CLIP READY` automatically. Optional punchline SFX
goes in `server/assets/sfx/`. `server/scripts/fetch-gameplay.sh` can pull
public-domain clips.

## The studio pipeline

1. **Model Connector** — pick an LLM provider + model (mock works offline)
2. **Topic / Prompt** — topic, tone, one-click idea chips → *Generate script*
3. **Script** — editable punchline-structured lines, word counts
4. **Voiceover / TTS** — provider + voice, free by default
5. **Gameplay / Background** — pick a gameplay loop with asset status
6. **Preview & Export** — readiness checklist → render → inline player

## API (v1)

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | liveness + ffmpeg/edge-tts capability probe |
| `GET /api/v1/models` | available LLM providers |
| `POST /api/v1/generate-script` | topic → meme script (mock/openai-compatible/ollama) |
| `GET /api/v1/voices?provider=edge` | TTS voice catalog |
| `POST /api/v1/tts` | synthesize one line → audio url |
| `GET /api/v1/render/gameplays` | gameplay clip catalog + availability |
| `POST /api/v1/render` | queue a render job (async) |
| `GET /api/v1/render/{job_id}` | poll job progress → `video_url` |

Interactive docs: http://localhost:8000/docs.

## Architecture notes

- **Render pipeline** — per-line TTS → duration probing (ffprobe) → caption
  timeline → Pillow caption PNGs + Reddit card → ffmpeg `overlay`/`vstack`
  compositor → H.264 1080×1920. Captions deliberately avoid ffmpeg's
  optional `drawtext` filter (absent from Homebrew builds) — works on any
  ffmpeg.
- **Resilience** — per-line TTS timeout + retries, ffmpeg/ffprobe subprocess
  timeouts, in-memory job store with progress polling.
- **CORS** — any `localhost`/`127.0.0.1` origin allowed in dev; set
  `MEMEFORGE_CORS_ORIGINS` for production.

## Templates

- Backend boilerplate: [`Icey-Python/fastapi-starter-boilerplate`](https://github.com/Icey-Python/fastapi-starter-boilerplate)
- Frontend template: [`zenetralabs/nextjs-template`](https://github.com/zenetralabs/nextjs-template) (Prisma/auth stripped)
