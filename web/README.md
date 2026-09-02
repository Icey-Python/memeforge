# Memeforge Web

Next.js (App Router, TypeScript, Tailwind CSS 4) frontend for memeforge with
an interactive React Flow canvas for building meme generation pipelines.

Based on the [zenetralabs/nextjs-template](https://github.com/zenetralabs/nextjs-template)
(Prisma and all auth/dashboard boilerplate stripped — this app is a studio
canvas, not a CRUD app).

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
| **Topic / Prompt**  | Enter the meme topic, pick a tone, trigger script generation     |
| **Script**          | Editable script lines; last line = punchline (gets the SFX)      |
| **Voiceover / TTS** | Provider (Edge-TTS free / Azure / ElevenLabs) + voice picker     |
| **Gameplay**        | Background loop picker (Minecraft Parkour, Subway Surfers, GTA…) |
| **Preview & Export**| Render trigger, job progress, vertical 1080×1920 video player    |

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
| `pnpm lint`       | ESLint                     |
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
│   └── catalog.ts           # offline fallback catalogs
├── store/pipeline.ts        # zustand pipeline + render job state
└── types/studio.ts          # shared types
```
