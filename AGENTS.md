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
- Stock stitch: `stitcher.py` downloads (size-capped) → `plan_clip_budgets` (repeat/trim to exact target) → ffmpeg concat into `background.mp4`; the renderer stitches AFTER TTS probing so the target is the exact final cut (probed audio + `VIDEO_TAIL_S`).

## API key vault & credential pass-through

- Frontend vault: `web/src/lib/vault-crypto.ts` (AES-GCM-256 + PBKDF2-SHA256 310k; localStorage holds ONLY ciphertext/salt/iv under `memeforge.api-key-vault.v1`) + `web/src/store/credentials.ts` (volatile zustand: `status` uninitialized/locked/unlocked, `keys` in memory only, `revision` bumped per save so queries refetch with fresh creds). UI: `settings-drawer.tsx` (Sheet; Lock Vault / Clear Vault two-step confirm) + `InlineVaultSection` embedded in voiceover/gameplay nodes. Never add a persist middleware or plaintext key to localStorage — captain directive.
- Credential priority everywhere: inline node input > vault key > server `.env`. LLM keys are host-matched in `web/src/lib/credentials.ts` `resolveLLMCredential` (openrouter/groq/anthropic by hostname, else OpenAI; unknown custom hosts get NO vault key — avoid silent exfiltration).
- Backend client-credential pass-through: `/tts` + `/voices` accept `elevenlabs_api_key`/`azure_speech_key`/`azure_speech_region` (query params or `X-Elevenlabs-Key`/`X-Azure-Key`/`X-Azure-Region` headers, headers win); `/stock/search` accepts `pexels_api_key`/`pixabay_api_key` (query or `X-Pexels-Key`/`X-Pixabay-Key`); `/render` takes the TTS fields in the body and forwards them into the render job. LLM `get_llm_provider` resolves gateway env keys by hostname (`registry.py` `_GATEWAY_KEYS`). `/health` capabilities expose server-default key presence booleans (`llm_*`, `tts_*`, `stock_*`) which drive the drawer's "Using Server Default" pills.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
