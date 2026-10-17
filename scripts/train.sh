#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${AAROGYA_ARTIFACT_DIR:-$ROOT_DIR/artifacts}"
PATIENTS="${AAROGYA_PATIENTS:-60}"
DAYS="${AAROGYA_DAYS:-5}"
SEED="${AAROGYA_SEED:-2026}"

PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" -m aarogya.pipeline \
  --output "$OUTPUT_DIR" \
  --patients "$PATIENTS" \
  --days "$DAYS" \
  --seed "$SEED"
