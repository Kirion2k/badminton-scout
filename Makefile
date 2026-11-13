UV ?= uv
RUN := cd backend && $(UV) run --locked

.PHONY: help setup db-up db-down migrate dev test lint format typecheck check \
	api-anything-install api-anything-doctor api-anything-test api-anything-smoke \
	sync schedule-install schedule-remove

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: ## install locked dependencies and create .env from the template
	cd backend && $(UV) sync --locked
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

db-up: ## start local PostgreSQL and wait until healthy
	docker compose up -d --wait db

db-down: ## stop local PostgreSQL (data volume kept; `docker compose down -v` deletes it)
	docker compose down

migrate: ## apply migrations to SCOUT_DATABASE_URL
	$(RUN) alembic upgrade head

dev: ## run the API with reload on http://127.0.0.1:8000
	$(RUN) uvicorn scout.main:app --reload --host 127.0.0.1 --port 8000

test: ## run all tests (needs `make db-up`)
	$(RUN) pytest

lint: ## ruff lint + format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

format: ## apply ruff fixes and formatting
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

typecheck: ## pyright strict
	$(RUN) pyright

check: lint typecheck test ## the quality gate: lint, types, tests (offline, deterministic)

api-anything-install: ## install the pinned API Anything runtime into tools/api-anything
	cd tools/api-anything && npm ci --ignore-scripts --no-audit --no-fund

api-anything-doctor: ## check node, the pinned runtime, and every approved operation
	$(RUN) scout api-anything doctor

api-anything-test: ## offline provider/adapter contract tests (no server, no network)
	$(RUN) pytest tests/test_provider.py

api-anything-smoke: ## LIVE: start the runtime and call the approved HN search operation
	$(RUN) pytest -m live -s tests/live

PLIST := $(HOME)/Library/LaunchAgents/com.badminton-scout.sync.plist

sync: ## LIVE: one scheduled pass (discover, refresh, import) within today's budget
	tools/scheduling/sync.sh

schedule-install: ## macOS: run `make sync` daily at 00:30 UTC via launchd (only while this Mac is on)
	@set -e; \
	hour=$$(/usr/bin/python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).replace(hour=0, minute=30).astimezone().hour)'); \
	sed -e 's|REPO|$(CURDIR)|g' -e "s|HOUR|$$hour|" tools/scheduling/com.badminton-scout.sync.plist > "$(PLIST)"; \
	plutil -lint "$(PLIST)" >/dev/null; \
	launchctl bootout gui/$$(id -u) "$(PLIST)" 2>/dev/null || true; \
	launchctl bootstrap gui/$$(id -u) "$(PLIST)"; \
	echo "scheduled daily at $$hour:30 local time (re-run after a daylight-saving change); log: .tools/sync.log"

schedule-remove: ## macOS: stop the daily sync
	-launchctl bootout gui/$$(id -u) "$(PLIST)"
	rm -f "$(PLIST)"
