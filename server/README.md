# Memeforge Server

FastAPI backend for memeforge: LLM script generation, TTS voiceover, and
full-screen vertical video rendering (1080x1920 Reddit-style shorts:
gameplay fills the frame, Reddit post card floats on top).

Based on the [fastapi-starter-boilerplate](https://github.com/Icey-Python/fastapi-starter-boilerplate)
project layout, adapted for the memeforge pipeline domain.

## Quickstart

```bash
cd server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Interactive docs are auto-generated from the OpenAPI schema.

## Endpoints

| Method | Path                       | Purpose                                        |
| ------ | -------------------------- | ---------------------------------------------- |
| GET    | `/health`                  | Liveness + capability report (ffmpeg, edge-tts) |
| GET    | `/api/v1/models`           | LLM connector catalog                          |
| POST   | `/api/v1/models/discover`  | Live model discovery (Ollama `/api/tags`, OpenAI-compatible `/v1/models`) |
| POST   | `/api/v1/generate-script`  | Generate a meme script for a topic             |
| GET    | `/api/v1/voices`           | Voice catalog (`?provider=edge\|tiktok\|azure\|elevenlabs`) |
| POST   | `/api/v1/tts`              | Synthesize speech, returns audio URL           |
| GET    | `/api/v1/render/gameplays` | Gameplay loop catalog                          |
| POST   | `/api/v1/render`           | Start an async render job                      |
| GET    | `/api/v1/render/{job_id}`  | Poll render job status / result video URL      |

## Architecture

```
app/
├── core/            # settings (env-driven) + app wiring
├── api/
│   ├── routers/     # main router (health + /api/v1)
│   └── endpoints/   # health, script, tts, render
├── providers/
│   ├── llm/         # model connectors: OpenAI-compatible, Ollama, mock
│   └── tts/         # voice connectors: edge-tts (free), TikTok meme voices
│                    # (free), Azure, ElevenLabs
├── services/
│   ├── jobs.py      # in-memory async render job registry
│   └── rendering/
│       ├── captions.py   # kinetic captions: 1-2 words/frame, center frame
│       ├── compositor.py # full-screen ffmpeg graph + Pillow reddit card
│       └── renderer.py   # pipeline orchestrator (TTS → captions → compose)
├── schemas/         # pydantic request/response models
└── utils/
    └── gameplays.py # gameplay loop catalog
```

### Render pipeline

1. `POST /api/v1/render` validates the request and queues a background job.
2. `renderer.run_render_job` synthesizes each script line with the selected
   TTS provider, measures durations with ffprobe, and stitches a voiceover.
3. `captions.build_caption_timeline` chunks the script into 1-2 word kinetic
   caption frames (last line is the punchline).
4. `compositor.build_reddit_post_card` renders the floating post card with
   Pillow: avatar + subreddit handle + verified badge + award emojis + bold
   title + like/comment/share metrics.
5. `compositor.compose_video` assembles an ffmpeg filter graph: the gameplay
   loop is scaled/cropped to fill the **full 1080x1920 frame**, the card is
   overlaid upper-center (fading out after the hook line, ~3-5s), and the
   caption PNGs burn in dead-center with heavy strokes
   (`[bg][card]overlay → caption overlays → drawtext-free H.264`).
6. The result lands in `outputs/` and is served at `/outputs/{job}.mp4`.

### TTS providers

| provider      | cost  | notes |
| ------------- | ----- | ----- |
| `edge`        | free  | Microsoft neural voices via edge-tts, no API key (default) |
| `tiktok`      | free  | classic TikTok meme voices (Jessie, Ghostface, Trickster…) via the unofficial WXA endpoint — keyless, but the mirrors can go dark (404); set `MEMEFORGE_TIKTOK_TTS_URLS` to a self-hosted proxy if needed |
| `azure`       | paid  | same neural voices with an SLA — set `AZURE_*` env |
| `elevenlabs`  | paid  | premium expressive voices — set `ELEVENLABS_API_KEY` |

### Adding a connector

- **LLM**: implement `BaseLLMProvider.generate_script()` in
  `app/providers/llm/`, then register it in `app/providers/llm/registry.py`.
- **TTS**: implement `BaseTTSProvider.synthesize()` in `app/providers/tts/`,
  then register it in `app/providers/tts/registry.py`.

## Gameplay assets

Drop vertical gameplay loops into `assets/gameplay/<id>.mp4` (see
`app/utils/gameplays.py` for catalog ids). A helper:

```bash
./scripts/fetch-gameplay.sh minecraft-parkour https://example.com/loop.mp4
```

Optional punchline SFX: drop any audio file into `assets/sfx/` (e.g.
`punchline.mp3`) and renders will mix it over the final punchline.

## Environment

Copy `.env.example` to `.env`. Everything works offline out of the box with
the `mock` LLM provider; real connectors need the keys listed there.

## Tests

```bash
pytest tests/ -v
```
