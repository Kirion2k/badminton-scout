# Badminton Scout design system (M5, premium badminton match centre)

Supersedes the M4 light editorial system. Direction: 70% refined sports intelligence, 20% athletic
energy, 10% editorial restraint. Not esports, not betting, not a newspaper.

## How it was chosen
- **UI/UX Pro Max** `--design-system "sports analytics match results live scores"` and the
  typography search picked the *Sports/Fitness* pairing: **Barlow Condensed** (headings, scores,
  labels) + **Barlow** (reading). Its team-red palette and the esports pairing (Russo One /
  Chakra Petch) were rejected: off-brief.
- **Benji Taylor evaluation** of M4: strongest dimension trust (provenance); most critical gap
  delight and identity, so the scoreboard and the tournament hero became the signature moments.
- **Brandkit** strategy: the court is the grid (data), the shuttle is the play (result).
- Two concepts were built and screenshotted: **A, Broadcast Match Centre** (all dark, timing-tower
  rows) and **B, Premium Athletic Intelligence** (light body, court-green hero, scoreboard cards).
  B was chosen: A's all-dark page and italic caps read as esports, and at desktop width the
  scores sat ~1000 px from the names. From A, B kept the lime winner lane and underline tabs.

## Brand
- **Mark:** a midnight crest holding a half court in thin lines and a lime shuttle in flight
  (cork, feather skirt, two ribs). Survives at 16 px (`web/src/app/icon.svg`,
  `components/brand.tsx`).
- **Wordmark:** BADMINTON **SCOUT**, Barlow Condensed 700, uppercase, Scout in lime.
- **Graphic language:** `.court-lines`, a half court drawn to scale (tramlines, service lines,
  centre line) at 13% white on dark heroes. Never on light surfaces, never animated.
- **Identity without photos:** players get a monogram crest (initials, lime base bar); federations
  get a country-code badge (AUS, NZL, SCO, GER, AUT, BRA, ENG, BEL, CAN, INT).

## Tokens (`web/src/app/globals.css`)
- Light: background `#f6f5f1`, card `#fff`, muted `#eceae3`, ink `#0b1526`, muted text
  `#545e6e`, subtle `#5c6576`, border `#e2dfd6`; win `#157a3c`, loss `#b42318`.
- Dark surfaces: midnight `#0b1526` (top bar, Discover, Tournaments, player, Coverage heroes),
  court green `#0d3b2c` (tournament match centre), muted text on them `#aab5c6` / `#a9c4b8`.
- Lime `#c8f031`: winner lane, active nav underline, primary action on dark, brand. Never text on
  light. All text pairs measured ≥ 4.5:1.
- Type: headings and figures Barlow Condensed 700 with tabular numerals; metadata labels
  condensed uppercase with 0.12em tracking; body Barlow 15 px.

## Structure
- **Shell:** midnight top bar (crest, sections with a lime underline that grows in, search with
  `/`); footer with data freshness. Below 1024 px: bottom tabs with a navy pill on the current tab.
- **Scoreboard** (`components/scoreboard.tsx`): header strip (event · round, status or date), one
  row per side, a lime lane bar on the winner, one fixed column per game actually played, the
  won game bold. Statuses: Completed, Score unavailable, Walkover, Retired, Disqualified, Not
  played. No LIVE state exists because no provider gives verified live data.
- **Tournament match centre:** court-green hero (federation, title, dates, place, organiser,
  events / matches / days, import state, source), discipline tabs MS · WS · MD · WD · XD on its
  edge (`?discipline=`, served by the API's discipline filter), event chips (a menu past 24
  events), then scoreboards grouped by event, or by round within one event.
- **Player:** athlete hero (monogram, disciplines, name, active span, Record / Matches decided /
  Win rate / Tournaments, last-10 form), then match history with filters, and a rail with results
  by discipline, doubles partners (latest 100 matches), tournaments and head-to-head.
- **Discover:** hero with search first and real totals as a strip; real scoreboards from the
  newest fully imported tournament (late rounds first); latest competitions; federation board.
- **Tournaments:** hero, filter rail with federation codes, month-grouped competition rows.
- **Coverage:** hero, totals card, freshness, federation ledger with codes and status chips.

## Rules carried over
- No fabricated numbers: no rankings, Elo or age, and nothing without a source.
- Colour never carries meaning alone: W and L letters, words for statuses, "Score unavailable"
  written out.
- Every page answers "where is this from?" within a glance (provenance line).
- Accessibility: axe passes in e2e, there is a skip link, focus is visible (navy on light, lime on
  dark surfaces), touch targets are ≥ 44 px on mobile, and reduced motion is respected (motion: 150–260 ms selected-state
  transitions and a score reveal, all off under `prefers-reduced-motion`).

## Responsive
- **≥ 1024 px:** midnight top bar with sections and search; scoreboards two per row.
- **< 1024 px:** top bar plus bottom tabs; discipline tabs and event chips scroll horizontally;
  scoreboards one per row, full width, scores never below 21 px.
- No horizontal page scroll at any width (tested at 390 px).

## Status codes under streaming (Next.js 16 Cache Components)
With Cache Components the shell streams first, so a `notFound()` inside a Suspense boundary
renders the not-found UI with HTTP 200 and an injected `noindex`. That's documented behaviour
(`guides/streaming`, "Status codes"). Restricted and unknown records show the same generic page.
