# Badminton Scout: design specification (M3)

A data product first: dense, calm and exact. A screen earns its space with real records, never filler.

## Navigation
- A slim top bar: wordmark on the left; **Discover**, **Tournaments**, **Coverage** on the right; a compact search field on every page except Discover, which *is* search.
- URLs are the state: `/?q=`, `/players/{id}?discipline=&tournament=&year=&result=&page=`, `/tournaments?q=&page=`, `/tournaments/{id}?event=&page=`, `/coverage`. Back/forward and sharing just work, and server rendering needs no client state.
- Canonical player URLs: a merged player's old URL redirects to the surviving one (the API answers 308; under streaming the page redirects client-side, see the last section).

## Layout
- Content max width 1200 px, 24 px gutters (16 px under 640 px).
- A page has a **header band** (title, one line of context, provenance), then its main content.
- Profile: a header with the record summary; then a two-column grid at ≥ 1024 px (match history 2/3, side panel 1/3 with tournaments and opponents), a single column below that.

## Typography
- **Geist Sans** for everything, with tabular figures (`.num`) for scores, dates and counts. Mono was dropped in the 2026-11-13 refinement because it made the data the loudest thing on the page.
- Scale: page title 32 px (26 px on phones), tracking −0.02em; row titles 15 px; body 14 px; meta 13 px; small 12 px; labels 11 px, uppercase, tracking 0.08em (`.label-quiet`).

## Surfaces, spacing, shape
- Surfaces lift by lightness, not by borders: page `--background`, panels `--card` with a 4 % white ring, controls and selected pills `--secondary`. Separators are 5–7 % white hairlines, and rows inside a panel are separated by space and a hover fill, not by lines.
- Spacing on a 4 px grid. Page top padding 40–56 px, header band to content 32 px, filter bar to results 20 px, list rows 14 px vertical padding.
- Radius: panels 12 px, rows and controls 8 px, pills full.
- One control shape (`.control`): 36 px tall, quiet white fill, hairline border, lime focus ring. Selects are native, so keyboards and phone pickers work.
- Lime marks only: focus, the active nav item (a 1 px underline), the selected pill, the winner dot. Routine buttons (Apply, Show, Previous/Next) are quiet; the lime button is reserved for Discover's search.

## Colour tokens (dark first; `:root` in `globals.css`)
| Token | Value | Use |
|---|---|---|
| `--background` | `#090e18` | page |
| `--card` | `#0e1522` | surface 1: panels, lists |
| `--secondary` | `#172032` | surface 2: controls, selected pills |
| `--border` | white 7 % | hairlines |
| `--foreground` | `#e8ecf3` | primary text |
| `--muted-foreground` | `#8d97aa` | secondary text (5.5:1 or better on every surface) |
| `--subtle` | `#808a9d` | tertiary meta: dates under rounds, counts (4.7:1 or better) |
| `--primary` | `#c6f432` (shuttle lime) | the one accent |
| `--win` / `--loss` | `#4ade80` / `#f87171` | won / lost |
| `--neutral-status` | `#94a3b8` | walkover, retired, not played: never painted as a win or a loss |

Contrast: every text pair is at least 4.5:1 (axe runs in the e2e suite), and lime on navy is 13:1. Colour never carries meaning alone: results show **W**/**L** letters, statuses show words, the winner dot has a screen-reader "(winner)".

## Components (shadcn/ui, restyled with the tokens)
- **SearchBox**: a GET form, so it works without JavaScript. Autofocused on Discover. `/` focuses it from anywhere.
- **ResultBadge**: W / L / W/O / Ret. / Not played. A walkover or retirement keeps its W or L, but is marked.
- **Score**: games as `21–15 · 21–18`, the viewed player's points first. On a tournament page a match is a two-line scoreboard: each side on its own line, one aligned column per game, the won game in bold, a lime dot before the winners.
- **Lists**: card/table hybrid rows. The title leads, the organiser and meta are quieter, and the whole row is the hit area (a stretched link, so only the title is a tab stop). Tournament matches are grouped by event under a quiet subheading.
- **PillLink / Select / MetaRow / SourceNote**: event pills, the native select, icon + text meta lines, and the quiet source line (`components/bits.tsx`).
- **MatchTable**: date · tournament · event · round · opponent(s) · score · result. Rows are links. On mobile each row becomes a two-line card.
- **FormStrip**: the last 10 decided results as W/L squares, oldest to newest. Undecided matches are left out, not counted as losses.
- **Provenance**: "Badminton Australia via Tournament Software · retrieved 12 Nov 2026" under every header that shows data.
- **Empty / Loading / Error**: skeleton rows the size of the real rows. Empty states say what was searched and what to try. Errors say what failed and offer a retry, never an internal message.

## Responsive behaviour
- ≥ 1024 px: the profile's two-column layout. 768–1023 px: one column, and the header shows the compact search. < 768 px: stacked match rows (score and result on their own line), wrapping filters, and the three nav links stay visible (they fit, so no menu button). The header's search is hidden on phones; Discover is one tap away.

## What we never show
Fabricated numbers: no rankings, Elo, age, country or "form score" without a source. Junior and para events are published by owner decision (ADR-0010). If that is reversed, the API filters them; the frontend never does.

## Status codes under streaming (Next.js 16 Cache Components)
Pages stream a prerendered shell before their data, so the HTTP status is `200` before the API is asked. A record that turns out missing *or restricted* renders the same generic "Nothing here" page, and Next.js injects `<meta name="robots" content="noindex">`. A merged player's redirect becomes a client-side redirect to the canonical URL. We accept this documented model (`node_modules/next/dist/docs/01-app/02-guides/streaming.md`, "Status codes") rather than adding an API lookup before every page. The privacy property, an identical response for restricted and non-existent records, is tested end to end.
