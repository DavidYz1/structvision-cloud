#!/usr/bin/env bash
# Run after: conda activate General

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT"
export KMP_DUPLICATE_LIB_OK="${KMP_DUPLICATE_LIB_OK:-TRUE}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

python worker/mamt2_worker_api.py
