# ADR-0007: API Anything as a first-class provider, gated per operation

Status: Accepted 2026-11-12 · Supersedes ADR-0002 §6 (API Anything) only. ADR-0002 §1–5 stand unchanged.

## Context
ADR-0002 kept API Anything out of production entirely. M1A built and verified the integration:
- the pinned 0.4.0 runtime and the official Python client;
- an `ApiAnythingProvider` that checks rights, calls at tier 1 only, classifies every result class and validates with Pydantic;
- a live smoke test against an approved public operation.

The remaining question is when an operation may run outside a developer's machine.

## Decision
API Anything is the default acquisition path for web sources that have no official API. Each **operation** (not each site) moves through five stages. Promotion between stages is a reviewed code change.

| Stage | Where | What is allowed | Gate to enter |
|---|---|---|---|
| 1. Discovery and learning | Developer machine, a separate learning home, never in `scout` code | `api-anything learn/capture/add/verify` against one page | Source has `LOCAL_RESEARCH` evidence in `data-sources.md`. Page not robots-disallowed. No login, no challenge bypass |
| 2. Offline adapter testing | CI | Fake transports and synthetic answers only | Always on. No network |
| 3. Approved read-only execution | Developer machine or job | `Provider.fetch()` of an entry in `scout.ingest.operations.OPERATIONS` | Operation registered with model, params and record key. Source has `LOCAL_RESEARCH`. Validation report in `docs/api-anything.md` |
| 4. Scheduled ingestion | Batch job (ADR-0001) | `fetch()` → `record_payload()` into revisioned raw records | Source has `STORE`. Accuracy and stability checks passed. Rate budget documented |
| 5. Production | Deployed job | As 4, with monitoring | Source has `STORE` + `REDISTRIBUTE` + `HOSTED` (ADR-0002 §4). Exported spec pinned in the repository. Drift and failure alerting live |

Rules at every stage:
1. **No learning at request time.** The runtime always starts with `--no-learn`, writes off and `API_ANYTHING_LOCAL_ONLY=1`, in an isolated `API_ANYTHING_HOME`. Nothing is pulled from or shared to the public catalog.
2. **Tier 1 only.** `fetch()` always sends `maxTier: 1`. Using browser tiers (2+) against a third-party site needs its own ADR.
3. **Default deny twice.** An unregistered operation raises `UnknownOperation`, and an ungranted source raises `SourceNotPermitted`, both before any request is sent.
4. **Judge by class, not by HTTP status.** Only `ok: true` with `class: "ok"` is success.
   - `rate` and `error` are retried only when the server's `retry` hint is `safe`, or `after_wait` within a 30 s cap. Attempts are bounded, and concurrency is capped per provider.
   - `auth`, `blocked`, `input`, `drift`, `refused`, `duplicate` and `pending` are never retried.
5. **Our schema is the contract.** Data that fails the operation's model raises `ResponseInvalid`, which is treated as drift. New, unknown upstream fields are logged.
6. **Provenance is unchanged:** fetched data enters the database only through `record_payload` (ADR-0005), which requires `STORE`. What is stored is the **source row as received** (`FetchResult.rows`), including fields our model ignores, not the validated model. The model decides validity and the row is the evidence. `record_payload` assumes one ingest job per source at a time: a concurrent first insert of the same key fails on the unique constraint instead of duplicating.

## Rejected
- **Letting the API learn or pull operations on demand.** That would execute unreviewed site specs against arbitrary hosts.
- **A generic provider plugin framework.** One `Provider` protocol and one implementation are enough until a second provider exists.
- **Blanket site-level approval.** Rights and reliability differ per page. For example, BWF's tournament pages and tournamentsoftware's player pages have different robots rules.

## Consequences
API Anything carries real traffic as soon as a source is permitted, with no further architecture work: register the operation, add evidence, promote. Until permission arrives, every badminton operation is blocked at stage 1. The only live operation today is the HN smoke test, which has `LOCAL_RESEARCH` only.
