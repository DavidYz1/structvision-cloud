#!/usr/bin/env bash
# Run after: conda activate mamt2-api
# Mock mode does not require the MAMT2 Worker service.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT/backend"
export USE_REAL_MAMT2=false

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
