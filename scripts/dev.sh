#!/usr/bin/env bash
# Run the memeforge monorepo dev stack: FastAPI on :8000 + Next.js on :3000.
# Usage: ./scripts/dev.sh  (Ctrl-C stops both)

set -euo pipefail
cd "$(dirname "$0")/.."

# --- backend ---------------------------------------------------------------
if [ ! -d server/.venv ]; then
  echo "==> Creating server venv"
  (cd server && python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements.txt)
fi
[ -f server/.env ] || cp server/.env.example server/.env

echo "==> Starting FastAPI on http://localhost:8000"
(cd server && .venv/bin/uvicorn app.main:app --reload --port 8000) &
SERVER_PID=$!

# --- frontend ---------------------------------------------------------------
if [ ! -d web/node_modules ]; then
  echo "==> Installing web dependencies"
  (cd web && pnpm install)
fi
[ -f web/.env ] || cp web/.env.example web/.env

echo "==> Starting Next.js on http://localhost:3000"
(cd web && pnpm dev) &
WEB_PID=$!

trap 'kill $SERVER_PID $WEB_PID 2>/dev/null || true' EXIT
echo ""
echo "memeforge dev stack ready:"
echo "  studio  → http://localhost:3000/studio"
echo "  api     → http://localhost:8000/docs"
echo ""
wait
