# memeforge

AI-powered Reddit-style meme video generator platform.

## Architecture

- **Web (`web/`)**: Next.js (App Router, TypeScript, Tailwind) with a React Flow interactive canvas for building modular meme generation pipelines.
- **Server (`server/`)**: FastAPI Python backend for LLM script querying (local/cloud models), Text-to-Speech synthesis (free Azure TTS / edge-tts, ElevenLabs), and video rendering/composition via FFmpeg (vertical 1080x1920 split-screen, gameplay loops, kinetic auto-captions, SFX).

## Templates

- Backend boilerplate: `git@github.com:Icey-Python/fastapi-starter-boilerplate.git`
- Frontend template: `git@github.com:zenetralabs/nextjs-template.git` (Prisma stripped)
