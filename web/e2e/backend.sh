#!/usr/bin/env bash
# Backend for end-to-end tests: a fresh *_e2e database, migrated and seeded with the synthetic
# fixture, served on 127.0.0.1:8770. Never points at the development or a production database.
set -euo pipefail
cd "$(dirname "$0")/../../backend"
UV="${UV:-uv}"
: "${E2E_DATABASE_URL:=postgresql+psycopg://scout:scout-dev-only@localhost:5433/scout_e2e}"
case "$E2E_DATABASE_URL" in *_e2e) ;; *) echo "E2E_DATABASE_URL must name a *_e2e database" >&2; exit 2 ;; esac

"$UV" run --locked python - "$E2E_DATABASE_URL" <<'PY'
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
url = make_url(sys.argv[1])
admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as c:
    if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": url.database}).scalar():
        c.execute(text(f'CREATE DATABASE "{url.database}"'))
PY

export SCOUT_DATABASE_URL="$E2E_DATABASE_URL" SCOUT_ENV=test
"$UV" run --locked alembic upgrade head
"$UV" run --locked scout seed e2e --ids-out ../web/e2e/fixture-ids.json
exec "$UV" run --locked uvicorn scout.main:app --host 127.0.0.1 --port 8770
