# Memeforge Server

FastAPI backend for memeforge: LLM script generation, TTS voiceover, and
vertical split-screen video rendering (1080x1920 Reddit-style shorts).

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
| POST   | `/api/v1/generate-script`  | Generate a meme script for a topic             |
| GET    | `/api/v1/voices`           | Voice catalog (`?provider=edge\|azure\|elevenlabs`) |
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
│   └── tts/         # voice connectors: edge-tts (free), Azure, ElevenLabs
├── services/
│   ├── jobs.py      # in-memory async render job registry
│   └── rendering/
│       ├── captions.py   # kinetic captions: 1-2 words/frame + drawtext escaping
│       ├── compositor.py # ffmpeg split-screen filter graph + Pillow reddit card
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
4. `compositor.build_reddit_card` renders the top-frame meme card with Pillow.
5. `compositor.compose_video` assembles an ffmpeg filter graph:
   `[card][gameplay] → vstack → drawtext captions (heavy stroke) + amix(sfx)`.
6. The result lands in `outputs/` and is served at `/outputs/{job}.mp4`.

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
