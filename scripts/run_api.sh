#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${AAROGYA_HOST:-127.0.0.1}"
PORT="${AAROGYA_PORT:-8000}"

cd "$ROOT_DIR"
PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" -m uvicorn aarogya.api:app \
  --host "$HOST" \
  --port "$PORT"
