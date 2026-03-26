#!/usr/bin/env bash
set -euo pipefail

# Start the FastAPI backend in the foreground
# Usage: ./scripts/start_backend.sh [PORT]

# Resolve repo root (one level up from this script dir)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR/backend"

# Activate virtual environment
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Load environment variables from .env if present
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${1:-${BACKEND_PORT:-5000}}"
LOG_FILE="${ROOT_DIR}/logs/backend.log"

mkdir -p "${ROOT_DIR}/logs"

echo "Starting backend (uvicorn) on port ${PORT}..."
echo "Logs will be written to: ${LOG_FILE}"
exec uvicorn main:app --port "${PORT}" --reload >> "${LOG_FILE}" 2>&1
