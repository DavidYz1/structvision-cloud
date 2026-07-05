#!/usr/bin/env bash
# Run after: conda activate mamt2-api
# Make sure the MAMT2 Worker is already running before starting real inference mode.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT/backend"
export USE_REAL_MAMT2=true
export MAMT2_WORKER_URL="${MAMT2_WORKER_URL:-http://127.0.0.1:9000}"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
