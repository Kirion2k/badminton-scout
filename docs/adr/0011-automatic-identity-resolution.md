# ADR-0011: Automatic identity resolution

Status: Accepted 2026-11-13. Amends ADR-0003: automatic links are now allowed, but only on
stable identifiers.

## Context
2,114 same-name candidates were waiting for review, and the owner does not want a permanent manual
queue. A false merge, two people combined, costs far more than a missed one. Member ids are scoped
by their issuing organisation (`member:<issuer GUID>/<id>`). Tournaments that publish no member id
give tournament-scoped records (`tplayer:`).

## Decision
`scout identity resolve` (also run after every scheduled sync, offline) decides each open or
deferred candidate:

1. **Tier A, deterministic: linked.** The same issuer and the exact same member id, with case,
   percent-encoding and invisible characters ignored, in any source. Ids that are equal only
   once punctuation is removed ("QA-1001" and "qa1001") also need the same name, because
   "1.2345" and "12.345" must not link. Placeholder ids ("-", "...") count as no id.
2. **Conflict: distinct.** Two records that played in the same tournament are two entries. This
   is checked across every record of both players before any merge, and a pair already resolved
   as distinct blocks other links between the same two players.
3. **Tier B, corroborated: off.** It would link a record without a member id to a member when
   the names match exactly, the tournament's issuer is the member's issuer, the name is unique
   among that issuer's members, and the two share a doubles partner. It is enabled only when, on at
   least 200 labelled negatives (different member ids, same name, same issuer), the **95% upper
   bound** of its false-link rate is at most 0.1%. That takes about 3,000 negatives with no
   error.
4. **Everything else: deferred.** The records stay separate, the reason is recorded, and they are
   re-checked on every run. No candidate is generated twice (a unique pair constraint).

Every link is an `IdentityDecision` by `auto:identity-resolver` and can be undone.
- **When a person undoes a link,** that is final: the candidate becomes `rejected` and is never
  linked again automatically.
- **People can still decide any open or deferred candidate** with `scout identity merge`, `reject`
  and `undo`.
- **A withheld player is never linked** (ADR-0010).
- **One resolver runs at a time,** under a global advisory lock. A failure in resolution never
  fails the sync that ran it.

## Evaluation (2026-11-13, real data)
- **Tier B recall:** 63.4% on 12,444 same-member pairs (a shared partner in another tournament).
- **Tier B false links:** **47.4%** on 599 namesake pairs. Partner overlap does not separate two
  namesakes from one person, so **Tier B is disabled**. The 13 links it made in a first run were
  reverted automatically (13 recorded `split` decisions).
- **The first measurement was rejected:** it only checked whether the rule found the right member
  among namesakes. That is trivially perfect once uniqueness is required, so it was replaced by
  the negative-pair test above.

## Results (2026-11-13)
- 2 Tier A links stand.
- 186 pairs were resolved as distinct (they played in the same tournament).
- 2,857 pairs are deferred:
  - 1,962 have no stable identifier on either record;
  - 895 have different member ids from one issuer (one person registered twice, or two people).

A deferred pair is not a review task: the records stay usable as separate players.
"Possible remaining duplicates" in `scout report identity` is an upper bound; many deferred
pairs are different people.

## What would enable more links
- A cross-system identifier: a BWF player id, or Tournament Software's global player profile id
  on `www.` (not captured yet).
- A second independent signal for tournament-scoped records: a club or a birth year. Neither is
  published in the data we use.
