# Memeforge Server

FastAPI backend for memeforge: LLM script generation, TTS voiceover, and
full-screen vertical video rendering (1080x1920 short-form videos: a
background loop fills the frame, an optional hook/quote card floats on
top).

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
| POST   | `/api/v1/generate-script`  | Generate a paced short-form script for a topic (`duration_target` 30/60/90s) |
| GET    | `/api/v1/voices`           | Voice catalog (`?provider=edge\|meme_classic\|tiktok\|google\|azure\|elevenlabs`) |
| POST   | `/api/v1/tts`              | Synthesize speech, returns audio URL           |
| GET    | `/api/v1/render/gameplays` | Background clip catalog                        |
| POST   | `/api/v1/render`           | Start an async render job (`card_style`: hook/quote/none) |
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
│   └── tts/         # voice connectors: edge-tts (free), Meme Classic
│                    # (Brian & co., free), TikTok meme voices (free,
│                    # auto-fallback), Google Translate TTS (free),
│                    # Azure, ElevenLabs
├── services/
│   ├── jobs.py      # in-memory async render job registry
│   └── rendering/
│       ├── captions.py   # kinetic captions: 1-2 words/frame, center frame
│       ├── compositor.py # full-screen ffmpeg graph + Pillow headline/quote card
│       └── renderer.py   # pipeline orchestrator (TTS → captions → compose)
├── schemas/         # pydantic request/response models
└── utils/
    └── gameplays.py # background clip catalog
```

### Render pipeline

1. `POST /api/v1/render` validates the request and queues a background job.
2. `renderer.run_render_job` synthesizes each script line with the selected
   TTS provider, measures durations with ffprobe, and stitches a voiceover.
3. `captions.build_caption_timeline` chunks the script into 1-2 word kinetic
   caption frames (last line is the punchline).
4. `compositor.build_headline_card` renders the optional top card with
   Pillow — `style="hook"` (bold headline) or `style="quote"` (oversized
   quote marks); `card_style="none"` renders a clean full video.
5. `compositor.compose_video` assembles an ffmpeg filter graph: the
   background loop is scaled/cropped to fill the **full 1080x1920 frame**
   (long assets start at a random seek in-point), the card is overlaid
   upper-center (fading out after the hook line, ~3-5s), and the caption
   PNGs burn in dead-center with heavy strokes
   (`[bg][card]overlay → caption overlays → drawtext-free H.264`).
6. The result lands in `outputs/` and is served at `/outputs/{job}.mp4`.

### Duration pacing

`POST /api/v1/generate-script` takes a `duration_target` (default 60s,
presets 30/60/90). Word budgets target ~2.2–2.5 words/sec of speech —
60s ≈ 130–150 words, the standard pacing for YouTube Shorts, TikTok, and
Reels — and the default line cap is ~4s of speech per line
(`word_target()` / `default_line_count()` in `app/providers/llm/base.py`).

### TTS providers

| provider       | cost  | notes |
| -------------- | ----- | ----- |
| `edge`         | free  | Microsoft neural voices via edge-tts, no API key (default) |
| `meme_classic` | free  | the iconic meme voices — Brian (British), Justin (kid/teen), Matthew (deep narrator), Kendra, Salli, Joey, Ivy, Joanna — via ttsmp3.com's free Polly-backed API. Keyless, no rate limits |
| `tiktok`       | free  | classic TikTok meme voices (Jessie, Ghostface, Trickster…) via the unofficial WXA endpoint — increasingly unstable for anonymous calls; set `TIKTOK_SESSION_ID` for logged-in access, and failed synthesis automatically falls back to edge-tts then Brian (`meme_classic`) |
| `google`       | free  | Google Translate TTS (`translate_tts`) — high-reliability fallback engine; voice id maps to the `tl` language code (en, en-GB…) |
| `azure`        | paid  | same neural voices with an SLA — set `AZURE_*` env |
| `elevenlabs`   | paid  | premium expressive voices — set `ELEVENLABS_API_KEY` |

### Adding a connector

- **LLM**: implement `BaseLLMProvider.generate_script()` in
  `app/providers/llm/`, then register it in `app/providers/llm/registry.py`.
- **TTS**: implement `BaseTTSProvider.synthesize()` in `app/providers/tts/`,
  then register it in `app/providers/tts/registry.py`.

## Background assets

Drop vertical background loops into `assets/gameplay/<id>.mp4` (see
`app/utils/gameplays.py` for catalog ids). Long clips (longer than the
requested video + 5s) automatically get a random seek in-point per render,
so repeated renders surface fresh footage. A helper:

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
