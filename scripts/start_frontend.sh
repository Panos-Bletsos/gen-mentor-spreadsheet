#!/usr/bin/env bash
set -euo pipefail

# Start the Streamlit frontend in the foreground
# Usage: ./scripts/start_frontend.sh [PORT]

# Resolve repo root (one level up from this script dir)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR/frontend"

# Activate virtual environment
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PORT="${1:-${FRONTEND_PORT:-}}"
LOG_FILE="${ROOT_DIR}/logs/frontend.log"

mkdir -p "${ROOT_DIR}/logs"

echo "Starting frontend (Streamlit) ${PORT:+on port ${PORT}}..."
echo "Logs will be written to: ${LOG_FILE}"
if [[ -n "${PORT}" ]]; then
  exec streamlit run main.py --server.port "${PORT}" >> "${LOG_FILE}" 2>&1
else
  exec streamlit run main.py >> "${LOG_FILE}" 2>&1
fi
