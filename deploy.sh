#!/usr/bin/env bash
# Deploy Nepali Legend Tracker to Railway (cloud — laptop can sleep).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env"
  exit 1
fi

if [[ ! -x ./node_modules/.bin/railway ]]; then
  echo "Installing Railway CLI locally…"
  npm install --prefix . @railway/cli
fi
export PATH="$(pwd)/node_modules/.bin:$PATH"
RAILWAY="$(command -v railway)"

if ! "$RAILWAY" whoami >/dev/null 2>&1; then
  echo "Open the browser to sign in to Railway, then re-run ./deploy.sh"
  echo "Or set RAILWAY_TOKEN from https://railway.app/account/tokens"
  "$RAILWAY" login
fi

if ! "$RAILWAY" status >/dev/null 2>&1; then
  echo "Creating Railway project…"
  "$RAILWAY" init --name nepali-legend-bot
fi

# Ensure a service exists
if ! "$RAILWAY" service status >/dev/null 2>&1; then
  echo "Creating bot service…"
  "$RAILWAY" add --service bot --json >/dev/null
  "$RAILWAY" service link bot || true
fi

# Ensure /data volume
if ! "$RAILWAY" volume list --json 2>/dev/null | grep -q '"mountPath": "/data"'; then
  echo "Adding /data volume…"
  "$RAILWAY" volume add --mount-path /data --json >/dev/null || true
fi

echo "Syncing env vars from .env…"
set -a
# shellcheck disable=SC1091
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

echo "Deploying (build runs in Railway’s cloud)…"
"$RAILWAY" up --detach -y

echo ""
echo "Live: https://railway.com/project/46e936de-295d-490e-b40a-f502e78edb74"
echo "Logs: railway logs"
echo "Local bot should stay stopped: ./stop.sh"
