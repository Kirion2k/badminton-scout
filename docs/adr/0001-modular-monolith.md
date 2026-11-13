# ADR-0001: Modular monolith, Postgres, batch ingestion CLI

Status: Accepted · 2026-11-12

## Context
One developer. About 100k historical matches, refreshed monthly at most. Read-heavy public UI.

## Decision
One Python package (`scout`) contains the FastAPI API, the ingestion CLI, identity tooling and analytics, deployed as one service. PostgreSQL is the only datastore, with `pg_trgm` for name search. The Next.js frontend talks only to the versioned API, using types generated from its OpenAPI document.

## Rejected
- **Separate ingestion service, queue (Celery/Redis), orchestrator (Airflow/Dagster):** a monthly batch of seconds' duration doesn't need them.
- **Elasticsearch/Meilisearch:** about 10k player names. Trigram search is enough.
- **Microservices:** no independent scaling or team boundaries to justify them.

## Revisit when
Ingestion runs longer than a request timeout on the deployment host, or live data is in scope.
