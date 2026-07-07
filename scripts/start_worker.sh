#!/usr/bin/env bash
# Run after: conda activate General

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"

cd "$PROJECT_ROOT"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

export KMP_DUPLICATE_LIB_OK="${KMP_DUPLICATE_LIB_OK:-TRUE}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MAMT2_DETECTRON2_ROOT="${MAMT2_DETECTRON2_ROOT:-$STACK_ROOT/detectron2}"
export MAMT2_MAIN_DIR="${MAMT2_MAIN_DIR:-$STACK_ROOT/detectron2/projects/MAMT2_main}"
export MAMT2_CONFIG_PATH="${MAMT2_CONFIG_PATH:-$STACK_ROOT/mamt2-artifacts/configs/config_ubuntu.yaml}"
export MAMT2_WEIGHT_PATH="${MAMT2_WEIGHT_PATH:-$STACK_ROOT/mamt2-artifacts/weights/model_best_segm.pth}"
export MAMT2_OUTPUT_DIR="${MAMT2_OUTPUT_DIR:-$PROJECT_ROOT/runtime/worker_outputs}"
export MAMT2_WORKER_HOST="${MAMT2_WORKER_HOST:-0.0.0.0}"
export MAMT2_WORKER_PORT="${MAMT2_WORKER_PORT:-9000}"

mkdir -p "$MAMT2_OUTPUT_DIR"

echo "[start_worker] PROJECT_ROOT=$PROJECT_ROOT"
echo "[start_worker] MAMT2_DETECTRON2_ROOT=$MAMT2_DETECTRON2_ROOT"
echo "[start_worker] MAMT2_MAIN_DIR=$MAMT2_MAIN_DIR"
echo "[start_worker] MAMT2_CONFIG_PATH=$MAMT2_CONFIG_PATH"
echo "[start_worker] MAMT2_WEIGHT_PATH=$MAMT2_WEIGHT_PATH"
echo "[start_worker] MAMT2_OUTPUT_DIR=$MAMT2_OUTPUT_DIR"
echo "[start_worker] MAMT2_WORKER_HOST=$MAMT2_WORKER_HOST"
echo "[start_worker] MAMT2_WORKER_PORT=$MAMT2_WORKER_PORT"

uvicorn worker.mamt2_worker_api:app --host "$MAMT2_WORKER_HOST" --port "$MAMT2_WORKER_PORT"
