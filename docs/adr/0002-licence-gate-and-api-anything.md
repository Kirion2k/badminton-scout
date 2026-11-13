# ADR-0002: Default-deny source rights gate. API Anything is not in the production data path

Status: Accepted (revised 2026-11-12) · Supersedes the 2026-11-12 proposal that used a `RESEARCH_ONLY` status · **§6 superseded by ADR-0007**

## Context
No third-party source has confirmed rights for any of our uses (`docs/data-sources.md`). The first draft labelled bwf-match-data `RESEARCH_ONLY` and let non-production environments serve it. That treated a label as permission, and it made "which environment am I in" the thing that decides legality.

API Anything (MIT, v0.4.0) needs a Node ≥ 22.13 server, doesn't read robots.txt, escalates to browser tiers when blocked, shares learned operations to a public catalog unless run `--local-only`, and has no badminton operations.

## Decision
1. **Rights live in code, per source and per use.** `scout.sources.SOURCES` maps each source ID to the set of `Use`s granted (`LOCAL_RESEARCH`, `STORE`, `REDISTRIBUTE`, `HOSTED`, `COMMERCIAL`), plus a non-empty evidence string. A grant is a reviewed code change, paired with a `data-sources.md` update.
2. **Fail closed.** `is_permitted(source_id, use)` returns `False` for an unknown source or an ungranted use. `require_permitted` raises. Ingestion and serving will call it before touching a source's records.
3. **Configuration can only restrict, never grant.** No environment variable, setting or database column can add a use. The `source` table holds descriptive metadata only.
4. **Environment adds requirements, never exemptions.** When `SCOUT_ENV=production`, serving a source also requires `HOSTED` and `REDISTRIBUTE`. `SCOUT_ENV` is required. A missing or unrecognised value fails settings validation at startup, so a deployment can't fall back to development rules.
5. Development and CI use only the `synthetic` source.
6. **API Anything:** allowed only in a time-boxed spike as a discovery tool, with `--local-only`, `maxTier: 1`, no login, and only on a page whose use is permitted in writing. Production ingestion uses first-party adapters only.

## Consequences
Today only `synthetic` data flows anywhere. Real data needs evidence, a PR and a review: slower, but impossible to enable by accident.
