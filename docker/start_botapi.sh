#!/bin/sh
# Dedicated Local Bot API for Rename Pipeline — only this process uses it
# Runs inside same Railway container to reuse 2core/1GB without extra server cost

set -e

if [ ! -x /usr/local/bin/telegram-bot-api ]; then
  echo "[botapi] telegram-bot-api binary not found — Local rename disabled, fallback to Cloud" >&2
  exec sleep infinity
fi

if [ -z "${TELEGRAM_API_ID:-}" ] || [ -z "${TELEGRAM_API_HASH:-}" ]; then
  echo "[botapi] TELEGRAM_API_ID/HASH not set — Local Bot API disabled, rename will fallback to Cloud (20MB limit)" >&2
  # Keep process alive as no-op so supervisord doesn't restart loop
  # Sleep forever
  exec sleep infinity
fi

# TELEGRAM_TOKEN is already required for bot
if [ -z "${TELEGRAM_TOKEN:-}" ]; then
  echo "[botapi] TELEGRAM_TOKEN not set — cannot start Local API" >&2
  exec sleep infinity
fi

# Use same Railway PORT is 8000 for API, so Local Bot API must be on different port
LOCAL_PORT="${TELEGRAM_LOCAL_API_PORT:-8081}"
if [ -z "${TELEGRAM_LOCAL_API_URL:-}" ]; then
  export TELEGRAM_LOCAL_API_URL="http://127.0.0.1:${LOCAL_PORT}"
  echo "[botapi] TELEGRAM_LOCAL_API_URL not set, defaulting to $TELEGRAM_LOCAL_API_URL" >&2
fi

API_ID="${TELEGRAM_API_ID}"
API_HASH="${TELEGRAM_API_HASH}"

# Directories — must be writable by humsyar user
DATA_DIR="/tmp/telegram-bot-api"
mkdir -p "$DATA_DIR/temp"
chmod 1777 "$DATA_DIR" "$DATA_DIR/temp" 2>/dev/null || true

echo "[botapi] Starting telegram-bot-api --local on $LOCAL_PORT with API_ID=$API_ID (hash ****)" >&2
echo "[botapi] Data dir: $DATA_DIR" >&2

# --local : store files locally, no need to re-download from Telegram for rename
# --http-port : Local API HTTP
# --dir : where to store files
exec /usr/local/bin/telegram-bot-api \
  --api-id="$API_ID" \
  --api-hash="$API_HASH" \
  --local \
  --http-port="$LOCAL_PORT" \
  --dir="$DATA_DIR" \
  --temp-dir="$DATA_DIR/temp" \
  --log="/tmp/telegram-bot-api.log" \
  --verbosity=2
