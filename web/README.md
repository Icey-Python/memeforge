# Memeforge Web

Next.js (App Router, TypeScript, Tailwind CSS 4) frontend for memeforge with
an interactive React Flow canvas for building short-form video pipelines.

## Quickstart

```bash
cd web
pnpm install
pnpm dev          # http://localhost:3000
```

Point it at the backend (FastAPI on :8000) via `.env`:

```
NEXT_PUBLIC_SERVER_URL=http://localhost:8000
```

## The Studio (`/` → `/studio`)

A React Flow (`@xyflow/react`) canvas with custom nodes:

| Node                | What it does                                                     |
| ------------------- | ---------------------------------------------------------------- |
| **Model Connector** | Choose the LLM (OpenAI-compatible / Ollama / offline mock)       |
| **Topic / Prompt**  | Enter the video topic, pick a tone + target duration (30/60/90s), trigger script generation |
| **Script**          | Generated or pasted custom script; every line editable, reorderable, removable; last line = punchline (gets the SFX) |
| **Voiceover / TTS** | Provider (TikTok meme voices / Edge-TTS / Azure / ElevenLabs) + voice picker with direct previews |
| **Gameplay**        | Background loop picker (Minecraft Parkour, Subway Surfers, GTA…) |
| **Preview & Export**| Card style (hook / quote / clean), render trigger, job progress, vertical 1080×1920 video player |

The Script node has two modes: **Generated** (LLM, paced to the duration
target) and **Custom** (paste/write your own script — it splits into timed
lines by paragraphs and punctuation, no LLM call, and instantly unlocks the
voiceover & gameplay steps).

Pipeline state lives in a zustand store (`src/store/pipeline.ts`); nodes
subscribe to the store so the whole graph stays in sync. The canvas itself
manages node/edge positions via `useNodesState`/`useEdgesState`.

## Stack

- Next.js 16 (App Router, Turbopack), React 19, TypeScript
- `@xyflow/react` 12 — the canvas
- Tailwind CSS 4 + shadcn/ui components (dark-first theme)
- zustand — pipeline state; TanStack Query — API queries
- sonner — toasts; lucide-react + Tabler icons

## Scripts

| Command           | Purpose                    |
| ----------------- | -------------------------- |
| `pnpm dev`        | Dev server (Turbopack)     |
| `pnpm build`      | Production build           |
| `pnpm typecheck`  | `tsc --noEmit`             |
| `pnpm lint`       | Biome check                |
| `pnpm lint-staged`| Biome on staged files      |

## Layout

```
src/
├── app/
│   ├── (home)/page.tsx      # landing hero
│   ├── studio/page.tsx      # full-height React Flow canvas
│   ├── layout.tsx           # dark mode root layout + toaster
│   └── globals.css          # Tailwind 4 theme (shadcn tokens)
├── components/
│   ├── studio/
│   │   ├── meme-canvas.tsx  # React Flow graph + toolbar
│   │   ├── studio-header.tsx
│   │   ├── node-shell.tsx   # shared node chrome (handles, header)
│   │   └── nodes/           # the six custom nodes
│   └── ui/                  # shadcn components
├── hooks/query/             # TanStack Query provider + keys
├── lib/
│   ├── config.ts            # axios apiBase → ${SERVER_URL}/api/v1
│   ├── memeforge.ts         # typed backend client
│   ├── catalog.ts           # offline fallback catalogs
│   └── script-split.ts      # custom-script text → timed lines
├── store/pipeline.ts        # zustand pipeline + render job state
└── types/studio.ts          # shared types
```
