# ADR-0014: Fixtures, forecast issuance and verified outcomes

Status: Accepted 2026-11-16. Builds on ADR-0005, ADR-0011, ADR-0012 and ADR-0013. ADR-0013's
release conditions are unchanged.

## Context
ADR-0013 counts only forecasts made before their match and scored against verified results. M8.1
issued forecasts against a date the operator typed in, and resolved them by finding a BWF match
within ±3 days. That cannot show a forecast came before the match, and no new BWF results arrive
anyway. M8.2 adds a provider-independent fixture record (`docs/data-providers.md`). Until BWF
provisions an official feed, the only provider is an operator entering fixtures by hand.

## Decision

### Source `bwf_curated`
- **What it is:** a person reads upcoming fixtures and results on `bwfbadminton.com` and enters
  them in a CSV kept outside git. That host is already in BWF's attested scope, so the grant is
  the same as `bwf`'s.
- **Not automated:** `scout fixtures import` reads the file, never the website. So `bwf_curated`
  has no hosts and no request budget.
- **Automated providers** go through the request budget of their own source (ADR-0008). Their
  credentials come only from environment variables.

### `fixture`
- **One row per source fixture key:** the current state.
- **Revisions:** every change is a new raw-record revision (ADR-0005), so corrections keep their
  history.
- **Contents:**
  - tournament;
  - discipline (MS/WS only);
  - round;
  - scheduled start (optional) and date;
  - IANA timezone;
  - status;
  - both sides as source players;
  - winner and score;
  - when the source data was checked (`retrieved_at`).
- **Players** are keyed by their BWF profile id. A curated row without one is rejected.
- **Duplicates:** a second key for the same pair, discipline and day is flagged `duplicate_of`.
  Neither fixture can be forecast.
- **Results count only when verified:**
  - by a different person from the one who entered them;
  - on the current revision. A later correction clears the verification.

### Player identity
- A fixture player is resolved when their source player belongs to a rated BWF player.
- That happens only through `scout identity link-fixture-player`: a person's decision, recorded
  as an identity candidate and merge. It can be undone (ADR-0003).
- Names never link a fixture player. Once linked, the same BWF profile id resolves again with no
  new decision.

### Issuing a forecast
`prospective.issue_for_fixture` refuses unless all of these hold:
1. **The fixture:**
   - it comes from an evidence source;
   - its status is `scheduled`;
   - it is not a duplicate;
   - its data was checked in the last 24 hours.
2. **No forecast exists** for the fixture (a unique column) or for the same match (M8.1's index).
3. **Both players** are resolved to current BWF players who pass `matchups.blocker`.
4. **The served ratings are current:** no BWF import finished after the served run.
5. **The time is before the cutoff:**
   - with a start time: 30 minutes before the start;
   - with a date only: 00:00 local time in the fixture's timezone. A fixture is never assumed
     unplayed because its day has not ended.

**Each forecast stores:**
- the fixture and the revision it saw;
- the cutoff;
- the probability, with M8.1's hashes, run and snapshot.

**Immutability:** a trigger forbids any update or delete.

### Outcomes
Computed from the fixture's current state when scoring, so the same database always gives the
same evaluation.

| State | Outcome |
|---|---|
| Verified `completed` with a winner | scored |
| `walkover`, `retired`, `abandoned` or `cancelled` | void (ADR-0012 eligibility) |
| The current revision's cutoff is at or before the issue time (the start moved earlier) | void |
| The fixture's players no longer resolve to the forecast's players (replaced, or a link undone) | void |
| A verified winner differs from an earlier verified winner | conflict: excluded and reported |
| Anything else (scheduled, postponed, live, unverified) | pending |

- **Audit trail:** `forecast_event` is append-only. It records void and conflict outcomes, and
  the reasons fixtures were refused a forecast.
- **The report:** every count is reported, so nothing that is excluded is hidden.

## Consequences
- **M8.1's date-based `issue` and ±3-day `resolve` are removed.** No forecast had been recorded,
  so nothing is lost.
- **Prospective evidence needs a person** to enter fixtures before play, to link about 300
  recurring players once each, and a second person to verify each result. That holds until an
  official feed exists.
- **Synthetic fixtures are never evidence.** Dry runs are rolled back, and only `bwf_curated`
  fixtures are issued.
