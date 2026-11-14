---
version: 1
slug: "web-src-app-players-id-page-tsx"
primary_target: "web/src/app/players/[id]/page.tsx"
related_targets: ["web/src/app/tournaments/[id]/page.tsx"]
---

## Scope
Player profile (web/src/app/players/[id]/page.tsx) and tournament detail (web/src/app/tournaments/[id]/page.tsx), then Discover, Tournaments, Coverage. Visitor mode: Operate.

## Direction contract
THESIS: Mynton is a badminton reference read like an umpire's scoresheet: ruled tables, fixed columns, the viewed player's points in ink. It refuses the hero-plus-stat-tiles-plus-cards dashboard every sports app ships.
OWN-WORLD: White ground; ink #14171a; form-print green #0b5d44 for rules, headings and won-result fills; ballpoint blue #1f3fbf reserved for "this player"; pencil grey #5d636b for the other side; loss red only on L marks. Archivo (75–100 width): condensed bold for names and headings, regular width for reading. No cards, no rounded panels, no eyebrows; hairline rules and a double-weight green rule under the summary.
STORY: The visitor learns who the player is, their record and form in one line, then scans every result by tournament with each game's score visible, then checks head-to-head and partners.
FIRST VIEWPORT: Top bar: wordmark left, search field dominant, section links. Name at 44px, a meta line (disciplines, federation, active span), the summary line (record, win rate, tournaments, last-10 W/L marks), then the results table begins above the fold; side column with by-discipline, head-to-head, partners.
FORM: Sports reference table in the umpire's-scoresheet world (grounded list position 7, brief Direction A). seed:942001961694ab5f
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
