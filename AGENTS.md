# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Validation commands

- Backend: `cd server && .venv/bin/python -m pytest tests/ -q` (venv lives in `server/.venv`; also `.venv/bin/python -c "import app.main"` for an import smoke test).
- Frontend: `cd web && pnpm typecheck && pnpm lint && pnpm build` (pnpm only; `pnpm lint` is biome — run `pnpm lint:fix` for auto-format, line width is 80).

## Sharp edges

- `web/src/hooks/query/keys.ts` is a query-key factory that no component imports; nodes use inline array keys (`['model-catalog']`, …). Follow the inline style.
- `web/.next/` build output is committed-adjacent clutter — never grep it; search `web/src` only.
- Studio canvas reveal animations (globals.css `.node-reveal`) must target the node's inner content (`.react-flow__node.node-reveal > *`), never the wrapper — the wrapper carries the inline positioning transform.
- Studio node visibility is gated by `studioStage()` in `web/src/store/pipeline.ts`; React Flow graph state stays in `meme-canvas.tsx` (display-filtered), don't move it into the store. A pasted custom script auto-confirms (`applyCustomScript`), which is what unlocks Voiceover/Gameplay — no LLM call.
- TTS/caption sync: `renderer.py` builds line durations from *probed* audio (never padded), `concat_audio` (compositor.py) stitches with the concat *filter* into WAV (gapless by default), and the final cut is audio + `VIDEO_TAIL_S` (0.3s tail). Live validation: `cd server && .venv/bin/python scripts/sync_check.py` (needs network for edge-tts).
- Duration pacing is single-sourced in `app/providers/llm/base.py` (`word_target()`, `default_line_count()`) with the frontend mirror in `web/src/lib/script-split.ts` (~2.2–2.5 words/sec, ~4s/line). Change both together.
- The tone id is `casual-commenter` (renamed from `reddit-commenter`); the top card is `build_headline_card(style="hook"|"quote")` — `card_style="none"` renders clean. Long background assets (> requested + `SEEK_MARGIN_S`) get a random seek in-point via `compute_background_seek`.
- The wizard is 5 steps now: `studioStage()` gates on `scriptConfirmed` → `voiceConfirmed` → `backgroundChosen` (see `web/src/store/pipeline.ts`). Background comes from either a preset loop (`gameplay_id`) or `stock_clips`; the render endpoint requires exactly one of the two.
- Stock video: providers live in `server/app/providers/stock/` (Pexels + Pixabay, portrait-only). Unkeyed mode serves curated demo clips from `pexels.py` — those CDN URLs can start 403ing over time, re-verify before relying on them. Keyword extraction (`stock/extract-keywords`) uses `complete_json` on the LLM providers with a heuristic fallback in `keywords.py`.
- Plug-and-play keys: the web UI has an encrypted browser vault (WebCrypto AES-GCM-256 + PBKDF2, `web/src/lib/vault-crypto.ts` + `store/vault.ts` + `components/studio/vault-key-input.tsx`) — secrets are NEVER persisted (pipeline store `partialize` excludes them; persisted blob lives under `localStorage['memeforge.vault.v1']`). Vault entry ids: `llm.{preset}.apiKey`, `tts.{provider}.apiKey`, `stock.{provider}.apiKey`. The backend accepts per-request overrides on top of server .env: `api_key`/`region` on `/tts` + `/voices`, `tts_api_key`/`tts_region` on render, `pexels_api_key`/`pixabay_api_key` query params on `/stock/search` (see `build_tts_provider` in renderer.py).
- Frontend LLM presets ≠ backend enum: `web/src/types/studio.ts` `LLMProviderId` has 7 presets (openai/anthropic/groq/openrouter/custom/ollama/mock) but the backend wire enum is only `openai|ollama|mock`. Every LLM request must map through `backendLLMProvider()` + `llmBaseUrl()` in `web/src/lib/catalog.ts` (cloud presets are fixed base URLs on the `openai` connector; anthropic is catalog-only, `discoverable: false`). The pipeline store is zustand-persisted with `skipHydration: true` — `MemeCanvas` rehydrates post-mount to avoid SSR mismatch on the prerendered `/studio` page.
- Stock stitch: `stitcher.py` downloads (size-capped) → `plan_clip_budgets` (repeat/trim to exact target) → ffmpeg concat into `background.mp4`; the renderer stitches AFTER TTS probing so the target is the exact final cut (probed audio + `VIDEO_TAIL_S`).

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
