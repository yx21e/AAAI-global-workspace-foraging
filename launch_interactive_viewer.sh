#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="${GWT_RUN_ID:-all-compete-v3}"
HOST="${GWT_HOST:-127.0.0.1}"
START_PORT="${GWT_PORT:-8765}"

cd "$PROJECT_ROOT"

if [[ ! -f "runs/qiyuan_integrated/${RUN_ID}_summary.json" ]]; then
  echo "Cannot find runs/qiyuan_integrated/${RUN_ID}_summary.json"
  echo "Set GWT_RUN_ID to an existing run id, or generate the run first."
  echo
  read -r -p "Press Enter to close..." _
  exit 1
fi

PORT="$(
  python3 - "$HOST" "$START_PORT" <<'PY'
import socket
import sys

host = sys.argv[1]
start = int(sys.argv[2])
for port in range(start, start + 50):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            continue
    print(port)
    raise SystemExit(0)
raise SystemExit(f"No free port found from {start} to {start + 49}.")
PY
)"

URL="http://${HOST}:${PORT}/"

echo "Starting interactive GWT viewer"
echo "Project: ${PROJECT_ROOT}"
echo "Run id:  ${RUN_ID}"
echo "URL:     ${URL}"
echo
echo "Use the browser page to load maps or rerun with language prompts."
echo "Keep this terminal open while using the viewer."
echo "Press Ctrl+C here to stop the server."
echo

PYTHONPATH=src:. python3 scripts/serve_qiyuan_viewer.py \
  --run-id "$RUN_ID" \
  --host "$HOST" \
  --port "$PORT" \
  --open
