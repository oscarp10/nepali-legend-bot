# Nepali Legend Ranked Tracker

Custom Discord bot for **Nepali Legend's** (`#R2J28R8Q`).

Tracks **Legend I / II / III** and **Electro League** players by clan membership + `leagueTier`. Posts CoC-style Battle Log cards and a live daily board.

## Run 24/7 (recommended — laptop can sleep)

Deploy to [Railway](https://railway.app) (free trial / hobby). The image builds **in their cloud**, so your Mac barely does any work.

```bash
chmod +x deploy.sh
./deploy.sh
```

1. Log in when the browser opens (or set `RAILWAY_TOKEN` from https://railway.app/account/tokens).
2. In Railway → your service → **Volumes** → add a volume mounted at `/data` (keeps `tracker.db`).
3. On this Mac: `./stop.sh` so nothing runs locally.

Optional: set `POLL_INTERVAL=90` (default in deploy) for lower CPU/API use.

## Docker (local, capped resources)

Only if you have Docker installed and want to test. Still dies when the laptop sleeps — use Railway for always-on.

```bash
docker compose up -d --build
docker compose logs -f
```

Hard limits: **0.25 CPU / 192 MB RAM**.

## Local (dev only)

```bash
cp .env.example .env   # set DISCORD_TOKEN=
./start.sh             # background
./stop.sh
tail -f data/bot.log
```

## Behavior

- Poll clan roster → track Legend / Electro tiers
- Editable Battle Log cards (attacks | defenses side by side) + Refresh button
- Live board in `#legend-league` / `#electro-feed`
- Day reset **05:00 UTC**
