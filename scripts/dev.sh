#!/usr/bin/env bash
# Start backend (127.0.0.1:8000) and frontend (127.0.0.1:5173) together.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYBIN="$ROOT/backend/.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="$(command -v python3)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && "$PYBIN" -m app.main) &
(cd "$ROOT/frontend" && npm run dev) &
echo "Backend:  http://127.0.0.1:8000/health"
echo "Frontend: http://127.0.0.1:5173"
wait
