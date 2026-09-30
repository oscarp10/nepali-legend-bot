#!/usr/bin/env bash
# Deploy Nepali Legend Tracker to Railway (runs in the cloud — laptop can sleep).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env"
  exit 1
fi

RAILWAY="$(pwd)/node_modules/.bin/railway"
if [[ ! -x "$RAILWAY" ]]; then
  echo "Installing Railway CLI locally…"
  npm install --prefix . @railway/cli
fi
export PATH="$(pwd)/node_modules/.bin:$PATH"
RAILWAY="$(command -v railway)"

if ! "$RAILWAY" whoami >/dev/null 2>&1; then
  echo ""
  echo "Open the browser window to log into Railway, then re-run: ./deploy.sh"
  echo "(Or set RAILWAY_TOKEN from https://railway.app/account/tokens )"
  "$RAILWAY" login
fi

# Create project/service on first run
if [[ ! -f .railway-linked ]]; then
  echo "Creating Railway project…"
  "$RAILWAY" init --name nepali-legend-bot || true
  touch .railway-linked
fi

echo "Pushing env vars from .env…"
# shellcheck disable=SC1091
set -a
source .env
set +a

"$RAILWAY" variables \
  --set "DISCORD_TOKEN=${DISCORD_TOKEN}" \
  --set "GUILD_ID=${GUILD_ID}" \
  --set "CLAN_TAG=${CLAN_TAG:-#R2J28R8Q}" \
  --set "COC_API_BASE=${COC_API_BASE:-https://proxy.clashk.ing/v1}" \
  --set "COC_API_KEY=${COC_API_KEY:-}" \
  --set "LEGEND_CHANNEL_ID=${LEGEND_CHANNEL_ID:-}" \
  --set "ELECTRO_CHANNEL_ID=${ELECTRO_CHANNEL_ID:-}" \
  --set "POLL_INTERVAL=${POLL_INTERVAL:-90}" \
  --set "DATA_DIR=/data"

echo "Deploying (build happens in Railway’s cloud)…"
"$RAILWAY" up --detach

echo ""
echo "Done. Attach a volume at /data in the Railway dashboard so tracker.db persists:"
echo "  https://railway.app → project → service → Volumes → Mount path /data"
echo ""
echo "Then stop the local bot so your laptop is free:"
echo "  ./stop.sh"
