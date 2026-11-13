# ADR-0009: Personal data of minors

Status: Accepted 2026-11-12. Superseded 2026-11-13 by [ADR-0010](0010-publish-junior-and-para-events.md): junior and para events are now published. The allowlist remains as the adult/restricted classifier.

## Context
Tournament Software's Badminton Australia portal includes junior events (`U11`–`U17`, "Junior") whose players are children. The authorisation as recorded covers storage and redistribution in general. It does not specifically address children's personal data, which privacy law and most federation policies treat separately.

## Decision
1. Junior data may be **stored** (raw revisions and domain tables) under the existing authorisation, so provenance stays complete.
2. It is **not redistributed**, meaning it never leaves through the API or UI, until a scope that explicitly covers minors' data is recorded in `data-sources.md`.
   - Events are classified as junior by name: an age marker `U\d+`, the word `junior`, or a boys'/girls' prefix (`BS`, `BD`, `GS` seen 2026-11-12; `GD` assumed by symmetry). The rule lives in one function.
   - API queries exclude junior events, plus players whose only matches are junior.
3. The classification fails closed: only an event with an adult discipline prefix (`MS`, `WS`, `MD`, `WD`, `XD`) and no age marker counts as adult. Anything else is treated as junior for redistribution.

## Consequences
Profiles of players who play both junior and adult events show their adult matches only. Lifting the restriction is a one-line change, made only alongside the recorded scope.

## Amendment 2026-11-12: para-badminton classes
Para events are named by sport class (`SH6`, `SL3`, `SL4`, `SU5`, `WH…`). A sport class reveals a **disability classification, which is health data**. Redistributing it is a separate scope that hasn't been established. These events have no recognisable adult discipline, so the same fail-closed rule already keeps them private (9 events on 2026-11-12). Lifting this needs its own recorded scope, distinct from minors.

## Amendment 2026-11-12 (review): allowlist, not denylist
The first rule hid names that matched junior markers. Review showed that it served `MS Under-17`, `MS Jnr`, `JMS`, `MS SL3` (a para class) and similar names. It is now an **allowlist** (`scout.privacy`):
- an event is served only if its name starts with `MS`/`WS`/`MD`/`WD`/`XD`;
- every following word must be a known adult-event word: grades A–E and combinations, Open, Reserve, Division N, masters ages 30+ / "plus", day and date labels, "Please see conditions".

Any other word keeps the event private. On the 737 real events the decisions are unchanged (309 served). The leak cases are tests. `U23` is hidden on purpose: some federations treat it as adult, but it is an age band, and failing closed is the rule.

Event flags are set when a match is written. After the rule changes, `scout privacy reclassify` re-applies it to every stored event without any requests. Migration 0005 leaves existing events private until that runs.
