# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Validation commands

- Backend: `cd server && .venv/bin/python -m pytest tests/ -q` (venv lives in `server/.venv`; also `.venv/bin/python -c "import app.main"` for an import smoke test).
- Frontend: `cd web && pnpm typecheck && pnpm lint && pnpm build` (pnpm only; `pnpm lint` is biome — run `pnpm lint:fix` for auto-format, line width is 80).

## Sharp edges

- `web/src/hooks/query/keys.ts` is a query-key factory that no component imports; nodes use inline array keys (`['model-catalog']`, …). Follow the inline style.
- `web/.next/` build output is committed-adjacent clutter — never grep it; search `web/src` only.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
