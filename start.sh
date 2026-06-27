#!/usr/bin/env bash
# One-command demo launcher.
#
#   ./start.sh
#
# Sets up both halves (idempotent), builds the frontend, and starts the backend
# which serves the UI *and* the API on a single URL. The patient store seeds all
# 5 synthetic patients automatically on first run — open the URL and go.
#
# No secrets required: lab triage, differentials, the imaging reads on the
# seeded patients, and referral letters all work without any API key. Add an
# OPENAI_API_KEY to .env only if you want live X-ray reads / the ID scanner.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"

echo "▶ clinic-dashboard demo setup"

# 1) .env — create from the example if missing (demo auth token, no API keys).
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  • created .env (demo token: clinic-demo-token; add OPENAI_API_KEY for live vision)"
fi

# 2) Backend: venv + deps.
cd backend
if [ ! -d .venv ]; then
  echo "  • creating Python venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "  • installing backend dependencies"
pip install -q --upgrade pip
pip install -q -r requirements.txt
cd "$ROOT"

# 3) Frontend: deps + production build (served by the backend).
cd frontend
if [ ! -d node_modules ]; then
  echo "  • installing frontend dependencies"
  npm install --silent
fi
echo "  • building frontend"
npm run build --silent
cd "$ROOT"

# 4) Run. Backend serves the built UI + the API on one port.
cd backend
echo ""
echo "✅ Ready. Open  http://localhost:${PORT}"
echo "   Sign in: the demo token is pre-filled — just enter your name."
echo "   (Ctrl-C to stop.)"
echo ""
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
