#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example to .env and fill DISCORD_TOKEN"
  exit 1
fi

# macOS Python often lacks system CA certs — point SSL at certifi
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"

exec .venv/bin/python -m bot.main
