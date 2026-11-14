# Mynton

Mynton (repository and code name: `badminton-scout`) is a badminton player-intelligence platform: search players, explore verified match history, follow form and compare players, with every number traceable to its source.

**Status:** player search, profiles, head-to-head comparison, tournament results and source coverage across several national federations and a third-party BWF historical compilation. Decisions: [`docs/adr/`](docs/adr), data rights: [`docs/data-sources.md`](docs/data-sources.md), design: [`DESIGN.md`](DESIGN.md).

**Name clearance (2026-11-14, not a legal opinion):** a web search found no "Mynton" product or trademark; similar marks exist in badminton (Crossminton, Redminton, Speedminton, BWF's AirBadminton). `mynton.com` is registered to someone else; `.app`, `.io` and `.com.au` did not resolve, which does not prove they are free. Before launch: formal searches of the USPTO, EUIPO, UK IPO and IP Australia registers in classes 9, 41 and 42, and a registrar check of the domains.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/) 0.13+
- Docker with Compose v2 (local PostgreSQL 18)
- GNU Make

## First-time setup

```sh
make setup      # uv sync --locked, and creates .env from .env.example
make db-up      # PostgreSQL on 127.0.0.1:5433 (not 5432, to avoid a native install)
make migrate    # alembic upgrade head
```

`.env` holds local development credentials only and is git-ignored. Any deployed instance must set `SCOUT_ENV=production` (ADR-0002).

## Run the API

```sh
make dev                                  # http://127.0.0.1:8000
curl http://127.0.0.1:8000/health         # liveness: {"status":"ok"}
curl http://127.0.0.1:8000/ready          # readiness: 200, or 503 when the database is unreachable
```

Interactive docs: http://127.0.0.1:8000/docs. Product endpoints:

| Endpoint | What |
|---|---|
| `GET /v1/players?q=` | name search, typo-tolerant (pg_trgm) |
| `GET /v1/players/{id}` | profile: record, tournaments, disciplines, sources, data freshness |
| `GET /v1/players/{id}/matches` | match history from the player's side, paginated |
| `GET /v1/tournaments/{id}` | tournament metadata and its events |

Junior and para events are served too, by owner decision (ADR-0010; ADR-0009 kept the classifier).

## Tests and quality gate

```sh
make test       # pytest. Needs `make db-up`. Uses a separate <db>_test database, recreated per run
make lint       # ruff check + format check
make typecheck  # pyright (strict)
make check      # all of the above. The same gate as CI
```

Tests use synthetic data only and never touch the network beyond the local database.

## API Anything (data acquisition)

Website operations run through a pinned, local-only [API Anything](https://github.com/goodnight000/api-anything) runtime (Node ≥ 22.13). See [`docs/api-anything.md`](docs/api-anything.md) and ADR-0007.

```sh
make api-anything-install   # pinned runtime into tools/api-anything
make api-anything-doctor    # node, runtime, approved operations
make api-anything-smoke     # LIVE: HN smoke + Tournament Software (BA). Not part of make check or CI
```

Badminton data (Tournament Software, Badminton Australia portal):

```sh
scout discover ba --pages 10                               # queue BA tournaments (20 per page, 1 request)
scout discover www --from 2025-08-01 --to 2025-11-14       # queue www badminton tournaments (owners resolved later)
scout import [--source ba|www|all] [--max 10]              # route owners, import completed tournaments; resumable,
                                                           # stops cleanly when today's budget is used up
scout import --tournament <GUID> [--renormalize]           # one queued tournament now
scout sync [--every 24]                                    # the scheduled pass (docs/operations.md)
scout report coverage                                       # per-source coverage and open issues
scout identity candidates | merge <id> | reject <id> | undo <decision> --reason "..."   # ADR-0003 review
scout privacy reclassify                                    # re-apply the serving rule to stored events (no requests)
```

Provider status (BWF and the other Tournament Software hosts are blocked on access methods): [`docs/badminton-providers.md`](docs/badminton-providers.md).

## Project structure

```
backend/
  src/scout/
    config.py     settings from SCOUT_* env vars; fails fast on missing or invalid values
    sources.py    data-source rights registry and default-deny gate (ADR-0002)
    models.py     source, ingest_run, raw_record, raw_record_revision (ADR-0005)
    db.py         engine and session
    ingest/       operations.py (approved ops), provider.py (fetch/classify/validate),
                  api_anything.py (local runtime), raw.py (revisioned ingest boundary),
                  tournamentsoftware.py (normalize + domain tables)
    api.py        /health, /ready
    api_v1.py     player and tournament read API (/v1)
    privacy.py    adult/restricted classifier and serving rule (ADR-0010)
    identity.py   identity candidates, merge, undo (ADR-0003)
    main.py       FastAPI app
    cli.py        `scout` command (`scout sources`)
  migrations/     Alembic
  tests/
docs/             kickoff report, ADRs, data-source register
compose.yaml      local PostgreSQL
Makefile          developer commands (`make help`)
```

The Next.js frontend will be added as `web/` in M3.

## Data rights

Only synthetic data may be stored, tested or served today. Third-party datasets must not be committed or loaded. See [`docs/data-sources.md`](docs/data-sources.md).
