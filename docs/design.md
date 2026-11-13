# Badminton Scout design system (M4, light editorial)

**Direction chosen:** *Editorial sports intelligence*: light, typography-led, quiet. This is the
second of two directions explored with the UI/UX Pro Max skill (`--design-system`).

- **A, "Vibrant & Block-based":** Bebas Neue, red. Rejected: loud fan-site energy, wrong for a
  data product.
- **B, "Minimalism & Swiss Style":** Fira Code, corporate blue. Its structure was kept, its
  palette and type were not.

The chosen result takes B's grid discipline, adds the skill's "News Editorial" pairing (a
Newsreader serif for display), and uses the owner's palette. The Benji Taylor evaluation of the
previous dark UI found the main gap was identity and delight; the structural changes below answer
that. Brandkit's "Light Editorial" mode set the brand strategy.

## Brand
- **Promise:** every match, traced to its source.
- **Mark:** a lime disc holding a cork circle and three fanned feather strokes (the shuttle's
  flight). It is used for the favicon, the sidebar and the badge.
- **Wordmark:** "Badminton Scout" in Newsreader semibold.
- **Tagline:** *Every match, traced.*

## Tokens (`web/src/app/globals.css`)
| Token | Value | Use |
|---|---|---|
| `--background` | `#f7f5f0` warm ivory | page |
| `--card` | `#ffffff` | the few raised surfaces (search, scoreboards) |
| `--muted` | `#efece4` | hover fills, quiet chips |
| `--foreground` | `#121a26` ink | text, 16:1 |
| `--muted-foreground` | `#5b6472` | secondary text, 5.1:1 or better |
| `--subtle` | `#626a77` | tertiary meta, 4.6:1 on every surface |
| `--border` | `#e3dfd5` | hairlines |
| `--primary` | `#c6f432` shuttle lime | fills and markers only, never text on ivory |
| `--primary-foreground` | `#121a26` | text on lime |
| `--accent-ink` | `#3f5a00` | lime-family text: links on hover, winner marks (7:1) |
| `--win` / `--loss` | `#1f7a3a` / `#b42318` | won / lost text (4.6:1 and 5.6:1 or better) |

- **Type:** Newsreader for display (page titles, section heads, big numbers); Geist Sans for the
  interface; tabular figures for every number.
- **Scale:** display 44/36/28 px, headings 20/17 px, body 15 px, meta 13 px, labels 11 px
  uppercase.
- **Radius:** 10 px on surfaces, 8 px on controls, full on chips.
- **Rules:** dividers are 1 px `--border`, not boxes. Sections are separated by space and a
  serif heading. Shadows only on the search field and on scoreboards (one soft shadow).

## Structure (what changed, not just how it looks)
- **Shell.** A **left sidebar** at ≥ 1024 px holds the mark and wordmark, the global player search,
  the sections (Discover, Tournaments, Coverage) and a live **data freshness** footer (last sync,
  next sync). Below 1024 px there is a top bar with the wordmark and search, and a bottom tab bar
  with the same three sections.
- **Discover.** An editorial hero: a serif headline with the live tournament, match and player
  counts, and one large search. Below it, *Federations* is a typographic index of real public
  coverage per federation (country, tournaments, matches), each row linking to its filtered list;
  then *Latest results*, recent tournaments with a date column.
- **Tournaments.** A **filter rail** (name, federation with live counts, year, discipline) beside a
  **results workspace** sorted by the chosen order. Rows are grouped under month headings, with a
  date block, the title, the federation and country, place, completeness and counts.
- **Tournament detail.** A header (federation kicker, serif title, a dates / place / organiser /
  size line, provenance, completeness note). Below it, a **sticky event navigator** groups events
  by discipline, and the **match workspace** shows matches grouped by round when one event is
  selected, or by event when all are. Matches are scoreboards.
- **Player profile.** An identity header (serif name, record W–L, matches, active span,
  last-10 form). Then **results by discipline** (computed from decided matches only), the match
  history with compact filters, and a side rail with tournaments and frequent opponents.
- **Coverage.** A hero sentence of real totals; a **federation ledger** with status, public
  tournaments and matches, span and last sync; pending providers (BWF) with the exact dependency;
  then the limitations. National coverage is never implied: each row says "N tournaments".

## Rules carried over
- No fabricated numbers: no rankings, Elo or age, and nothing without a source.
- Colour never carries meaning alone: W and L letters, words for statuses, "Score unavailable"
  written out.
- Every page answers "where is this from?" within a glance (provenance line).
- Accessibility: axe passes in e2e, there is a skip link, focus is visible (an ink outline on
  ivory), touch targets are ≥ 44 px on mobile, and reduced motion is respected (motion is limited
  to 150 ms colour transitions).

## Responsive
- **≥ 1280 px:** sidebar, two-column workspaces.
- **1024–1279 px:** sidebar, single-column workspaces with the rail below.
- **< 1024 px:** top bar plus bottom tabs; filters collapse into a disclosure; scoreboards stay
  two-line.
- No horizontal page scroll at any width (tested at 390 px).

## Status codes under streaming (Next.js 16 Cache Components)
With Cache Components the shell streams first, so a `notFound()` inside a Suspense boundary
renders the not-found UI with HTTP 200 and an injected `noindex`. That's documented behaviour
(`guides/streaming`, "Status codes"). Restricted and unknown records show the same generic page.
