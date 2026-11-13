# Badminton Scout

A badminton player-intelligence app. Python modular monolith in `backend/` (FastAPI + SQLAlchemy + Alembic + Postgres). A Next.js frontend in `web/` arrives in M3. Roadmap: `docs/kickoff-report.md` §12. Commands: `make help`.

## Rules that apply to every change
- **Data rights are default-deny.** Read `docs/data-sources.md` before touching any source. Only `synthetic` data may be stored (`hacker_news_smoke` is a transient smoke test only), so tests, fixtures and dev seeds are synthetic. Never add third-party records to git or CI. Grants live only in `backend/src/scout/sources.py`, paired with evidence in `data-sources.md`. Never add a config or env switch that grants a use (ADR-0002). Never send automated requests to a robots.txt-disallowed path, and never bypass a 403, challenge, login or cookie wall.
- **Provenance.** Every stored record keeps its source, source record key, payload revision and ingest run (ADR-0005). Scores are never part of a record key.
- **Provider authorisations (ADR-0008).** Each authorised source lists its hosts and request budget in `sources.py`. Never add a host, or treat a sister site as covered, without recorded scope. A robots exception never covers logins, challenges or consent walls.
- **API Anything (ADR-0007).** Only operations in `scout/ingest/operations.py` are ever called, always at tier 1, through a `--no-learn`, local-only runtime. Learning happens only in the documented workflow (`docs/api-anything.md`), in a separate home, for sources with evidence. Never run `api-anything setup`, `publish` or `pull`, and never `login` except through `scout.ingest.consent` (consent cookie from a file, ADR-0008). Record every manual request with `scout budget record`.
- **Identity.** Never merge players automatically on a fuzzy match (ADR-0003).
- **Boundaries.** Only `scout/ingest/` talks to external sources, and only through approved operations. `analytics/` is pure. `web/` talks only to `/v1` with generated types (`web/src/lib/api.gen.ts`, never hand-edited).
- **Tests.** No live third-party requests in the default test run or CI (`-m live` tests are run explicitly only). Fixtures are synthetic (fake API Anything answers in `tests/test_provider.py`). New parsing or analytics logic comes with tests. Rating and prediction code needs a chronological split and a leakage check.
- **Verification.** Run `make check` before saying something works, and report the actual output.
- **Never** commit, push, merge, deploy or change `../badminton-poc` without the owner's approval.

## Decisions
Architecture decisions live in `docs/adr/`. Follow them, or propose a new ADR that supersedes one.
