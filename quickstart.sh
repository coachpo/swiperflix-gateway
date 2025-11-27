#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

# Prefer local virtualenv when present
if [[ -f ".venv/bin/activate" && "${VIRTUAL_ENV:-}" != "$SCRIPT_DIR/.venv" ]]; then
  echo "Activating .venv ..."
  # shellcheck source=/dev/null
  source ".venv/bin/activate"
fi

echo "Swiperflix Gateway quick start"
echo "1) Populate data (python -m app.sync)"
echo "2) Start server (python -m uvicorn app.main:app --reload --host 0.0.0.0)"
echo "q) Quit"
read -rp "Select an option: " choice

case "$choice" in
  1)
    python -m app.sync
    ;;
  2)
    python -m uvicorn app.main:app --reload --host 0.0.0.0
    ;;
  q|Q)
    echo "Bye"
    exit 0
    ;;
  *)
    echo "Invalid choice" >&2
    exit 1
    ;;
esac
