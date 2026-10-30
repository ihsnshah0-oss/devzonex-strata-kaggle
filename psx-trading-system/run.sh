#!/usr/bin/env bash
# PSX Trading System launcher (macOS / Linux)
# Usage: ./run.sh [port]  → default port 8111, e.g. ./run.sh 8005
# Then open http://localhost:8111  (phone: http://<laptop-ip>:8111)
cd "$(dirname "$0")"
PORT="${1:-${PSX_PORT:-8111}}"
python3 -m pip install -q -r requirements.txt
echo "Starting PSX Live & Research on http://0.0.0.0:${PORT} ..."
python3 -m uvicorn src.app.server:app --host 0.0.0.0 --port "$PORT"
