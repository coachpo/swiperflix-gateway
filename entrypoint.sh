#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

echo "Populating data via python -m app.sync ..."
python -m app.sync
echo "Data population complete. Starting server on ${HOST}:${PORT} ..."

# Replace shell with uvicorn so it receives signals correctly (useful in Docker)
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
