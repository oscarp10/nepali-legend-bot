#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PID_FILE="data/bot.pid"

if [[ ! -f "$PID_FILE" ]]; then
  pkill -f "python -m bot.main" 2>/dev/null || true
  echo "Stopped (no pid file)"
  exit 0
fi

pid="$(cat "$PID_FILE")"
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "Stopped pid $pid"
else
  echo "Process $pid not running"
fi
rm -f "$PID_FILE"
