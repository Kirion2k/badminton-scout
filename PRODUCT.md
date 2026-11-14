# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Competitive, club and university badminton players, coaches, and tournament followers researching
players and past results. Two equal situations (confirmed): on a phone at a venue, checking the
next opponent between matches; and on a laptop, preparing before a tournament or for coaching.

## Product Purpose
Mynton is a global badminton reference and opponent-intelligence product. It answers one question
fast: who is this player, what have they played, how have they performed, and what can I learn
about them? Success is a player or coach reaching a trustworthy answer in seconds, on either device.

## Positioning
Confirmed by the owner, and true only here:
- **One player across federations.** Records from many national Tournament Software portals are
  joined into one player history with conservative, reversible identity linking (ADR-0011).
- **Every number sourced.** Each result keeps its source, retrieval time and import completeness;
  missing data is stated, never filled in.
- **Opponent preparation.** Head-to-head, doubles partners and recent form, framed for preparing to
  play someone.

## Operating Context
Data comes from authorised Tournament Software portals (Australia, New Zealand, Scotland, Germany,
Austria, Brazil, England, Flanders, the global site; Canada partial; BWF pending access), imported
daily. Pages read only the project database. Results include junior and para events (ADR-0010).

## Capabilities and Constraints
- Player search (typo tolerant), player profile with record, form, by-discipline record,
  tournaments, frequent opponents (head-to-head), doubles partners, filtered match history.
- Tournament list (filters: name, place, year, discipline, federation; sorts) and tournament detail
  (events, disciplines MS/WS/MD/WD/XD, rounds, matches with per-game scores).
- Match statuses: completed, walkover, retired, disqualified, winner known with score unavailable,
  not played. Unknown outcomes never count as wins or losses.
- No live scores, rankings, ratings, seedings, court numbers, durations, player photos, ages or
  nationalities per player: the sources do not provide them, so they are never shown.
- Withheld players appear as "Name withheld" and are never linked.
- Frontend: Next.js 16 talking only to the FastAPI `/v1` contract with generated types.

## Brand Commitments
- Name: **Mynton** (owner decision, 2026-11-14; from bad-*mynton*). Repository and code names stay
  `badminton-scout` unless the owner changes them.
- No other identity element is binding: the previous crest, lime accent and condensed type may be
  replaced.

## Evidence on Hand
~100,000 public matches, ~340 tournaments, ~50,000 players in the local database (real data, never
committed). Synthetic fixtures in `web/e2e` and `backend/tests`. No testimonials, users, rankings or
photography exist; none may be invented.

## Product Principles
1. The answer first: a player's record and recent results before anything decorative.
2. Provenance is part of the interface, not a footnote.
3. Absence is information: say what is missing or unavailable, plainly.
4. Dense where people scan, generous where people read; never padding for its own sake.
5. Equal care for the phone at the venue and the laptop at home.

## Accessibility & Inclusion
WCAG 2.1 AA: axe-clean pages in the e2e suite, keyboard reachable, visible focus, 44 px touch
targets on mobile, reduced motion respected, meaning never by colour alone.
