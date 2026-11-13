# ADR-0005: Source record identity, revisions, collisions and normalized matches

Status: Accepted 2026-11-12 · `raw_record` and `raw_record_revision` implemented in M0. The rest in M2

## Context
The first draft keyed records by a hash that included the score. A source correcting a score would then create a second "match" instead of a revision of the first. Sources without native match IDs also produce genuinely ambiguous rows.

## Decision
Four separate concepts:

1. **Source record identity:** `raw_record (source_id, source_record_key)`, unique.
   - With a native ID, the key is that ID.
   - Without one, the key is a *locator* built only from fields that identify the fixture and do not get corrected: `date|tournament|discipline|round|sorted(side keys)`.
   - Scores, winners and other mutable outcome fields are **never** part of the key.
2. **Revision:** `raw_record_revision (raw_record_id, content_sha256)`, unique.
   - Holds the full payload, `first_seen_run_id` and `last_seen_run_id`.
   - Identical content seen again only updates `last_seen_run_id`.
   - Different content is a new revision, and `raw_record.current_revision_id` moves to it. Older revisions are kept, so corrections are visible and nothing is silently overwritten.
3. **Normalized match** (M2): `match.raw_record_id` is unique, so each source record produces at most one match, rebuilt from its current revision. `match.normalized_from_revision_id` records which revision.
4. **Collisions and duplicates** (M2):
   - Two different rows in *one* run that share a locator key are an `ingest_issue(kind='key_collision')`. Neither becomes a match until a human resolves it, for example by adding a disambiguating field to that source's locator.
   - The same real match appearing in two sources is a *cross-source duplicate*, handled later by a candidate table like `identity_candidate`. It is not resolved by merging rows.

`ingest_run` records each execution with its status and counts (`new`, `revised`, `unchanged`, `rejected`, `collisions`).

## Consequences
Re-ingesting an unchanged file writes no new revisions. A corrected score shows up as a revision on the same match. Ambiguous source data surfaces as issues instead of guesses.
