#!/bin/sh
# Daily scheduled sync: run by launchd (this Mac), cron or a systemd timer (docs/operations.md).
# Settings come from the repo .env via scout.config; Postgres must be running (make db-up). Runs that overlap are safe: each provider is
# locked in Postgres, and every request is counted in the shared ledger.
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# launchd starts with a bare PATH: add where node (API Anything runtime) is usually installed
export PATH="$ROOT/.tools/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH" UV_CACHE_DIR="$ROOT/.tools/uv-cache" UV_PYTHON_DOWNLOADS=never
cd "$ROOT/backend"
# a full day's budget takes hours at 5 s a request: keep the Mac from idle-sleeping meanwhile
KEEP_AWAKE=""
command -v caffeinate >/dev/null && KEEP_AWAKE="caffeinate -i"
exec $KEEP_AWAKE uv run --locked scout sync --every "${SCOUT_SYNC_EVERY_HOURS:-24}"
