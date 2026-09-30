# Minimal image — runs off your laptop once deployed to Railway/Fly/etc.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data

WORKDIR /app

# System deps kept tiny (certs only)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

RUN mkdir -p /data \
    && useradd --create-home --uid 10001 bot \
    && chown -R bot:bot /app /data

USER bot

CMD ["python", "-m", "bot.main"]
