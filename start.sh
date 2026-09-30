#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PID_FILE="data/bot.pid"
LOG_FILE="data/bot.log"
mkdir -p data

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Already running (pid $(cat "$PID_FILE"))"
  exit 0
fi

# Clear stale pid
rm -f "$PID_FILE"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example to .env and set DISCORD_TOKEN"
  exit 1
fi

export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"

# Detach from the controlling terminal / agent shell so the bot survives
# after the starter exits (macOS often reaps non-detached children).
if command -v setsid >/dev/null 2>&1; then
  setsid .venv/bin/python -u -m bot.main >>"$LOG_FILE" 2>&1 < /dev/null &
else
  nohup .venv/bin/python -u -m bot.main >>"$LOG_FILE" 2>&1 < /dev/null &
fi
echo $! > "$PID_FILE"
disown "$!" 2>/dev/null || true

sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Failed to start — see $LOG_FILE"
  exit 1
fi

echo "Started Nepali Legend Tracker (pid $(cat "$PID_FILE"))"
echo "Logs: $LOG_FILE"
