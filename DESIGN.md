---
name: Mynton
description: A badminton reference read like an umpire's scoresheet; every number traced to its source.
colors:
  ink: "#14171a"
  paper: "#ffffff"
  form-green: "#0b5d44"
  ballpoint-blue: "#1f3fbf"
  pencil-grey: "#5d636b"
  loss-red: "#a3271c"
  wash: "#f2f4f1"
  sheet-rule: "#b9c7bf"
  hairline: "#dcdfd9"
  control-edge: "#c3c8c0"
  selection: "#d6def8"
typography:
  display:
    fontFamily: "Archivo, sans-serif"
    fontSize: "46px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.012em"
    fontVariation: "'wdth' 78"
  headline:
    fontFamily: "Archivo, sans-serif"
    fontSize: "42px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.012em"
    fontVariation: "'wdth' 78"
  title:
    fontFamily: "Archivo, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.45
    fontVariation: "'wdth' 80"
  body:
    fontFamily: "Archivo, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "'tnum'"
  label:
    fontFamily: "Archivo, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  mark:
    fontFamily: "Archivo, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "'tnum'"
rounded:
  mark: "3px"
  control: "4.8px"
  tab-group: "6px"
spacing:
  gutter-phone: "16px"
  gutter: "32px"
  column-gap: "48px"
  row-pad: "8px"
  container: "1240px"
components:
  button-primary:
    backgroundColor: "{colors.form-green}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 24px"
    height: "48px"
  button-quiet:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "36px"
  button-quiet-hover:
    backgroundColor: "{colors.wash}"
  input-search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px 0 40px"
    height: "48px"
  mark-won:
    backgroundColor: "{colors.form-green}"
    textColor: "{colors.paper}"
    typography: "{typography.mark}"
    rounded: "{rounded.mark}"
    size: "22px"
  mark-lost:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.loss-red}"
    typography: "{typography.mark}"
    rounded: "{rounded.mark}"
    size: "22px"
  status-note:
    backgroundColor: "{colors.wash}"
    textColor: "{colors.ink}"
    rounded: "{rounded.mark}"
    padding: "2px 6px"
  tab-current:
    backgroundColor: "{colors.form-green}"
    textColor: "{colors.paper}"
    height: "40px"
    padding: "0 14px"
---

# Design System: Mynton

## Overview

**Creative North Star: "The Umpire's Scoresheet"**

Mynton is a badminton reference that reads like the sheet an umpire fills in at courtside: a white ground, ruled lines printed in form green, the scores entered in ink, the viewed player's own points in ballpoint blue, the other side in pencil grey. Structure comes from rules and fixed columns, never from boxes. A page is one long ruled document with a narrow side column, dense enough to scan a whole season of results, quiet enough that the numbers are the only loud thing on it.

The system deliberately refuses the sports-app dashboard: no hero banner, no stat tiles, no card grid, no photography, no court illustrations. Its one typeface, Archivo, carries two voices through its width axis: condensed bold for names and headings, regular width for reading and figures. All figures are tabular so columns of scores line up like a printed sheet.

The scoresheet is also a promise about truth. Every value on screen was published by a source; what a source did not publish is written as absent, never drawn as a placeholder number.

**Key Characteristics:**
- White paper, ink text, one structural colour (form green) and one personal colour (ballpoint blue).
- Hairline rules and green section rules in place of cards and panels.
- One family, two widths: Archivo condensed for names and headings, normal width for reading.
- Tabular figures everywhere; scores in fixed per-game columns.
- Meaning carried by letters and words (W, L, "Score unavailable"), colour only reinforcing.
- Flat: no shadows, no gradients, no imagery.

## Colors

A printed-form palette: ink on white with form-print green for structure, and two reserved signal colours.

### Primary
- **Form Green** (form-green): the colour of the printed form. Section rules and section headings, the 2px rule above a player's summary line, won-result marks (filled W squares), the current discipline tab and filter, the primary Search button, the wordmark, and the win share in by-discipline bars. 7.9:1 on paper.

### Secondary
- **Ballpoint Blue** (ballpoint-blue): reserved for "this player". It colours only the viewed player's row in the GameSheet scoresheet cell, and the focus ring (2px outline, 2px offset). 8.3:1 on paper.

### Tertiary
- **Loss Red** (loss-red): only the letter L in a lost-result mark (outlined, never filled) and written loss statuses. 7.3:1 on paper.

### Neutral
- **Ink** (ink): all primary text, winning game scores, names. 18:1 on paper.
- **Paper** (paper): the page ground and every surface. There is no second surface colour for panels.
- **Pencil Grey** (pencil-grey): secondary text, the losing side's scores, meta lines, source notes, icons, placeholders. 6.1:1 on paper, 5.5:1 on wash.
- **Wash** (wash): the faint tint of an opened scoresheet row, row hover, quiet-button hover, and the status-note ground.
- **Sheet Rule** (sheet-rule): the ruled lines inside the GameSheet cell.
- **Hairline** (hairline): row dividers, the top bar's lower edge, the footer rule.
- **Control Edge** (control-edge): borders of inputs, selects, quiet buttons and the tab group.
- **Selection** (selection): text-selection highlight, a pale blue echoing the ballpoint.

### Named Rules
**The Two Pens Rule.** Ballpoint blue means "the player you are viewing" and nothing else (the focus ring is the only other use). Green structures the sheet; blue is the person.

**The Letter First Rule.** Colour never carries meaning alone. A result is W or L, a status is written out ("Walkover", "Retired", "Score unavailable"); green and red only reinforce the letter.

**The 4.5 Floor Rule.** Every text pair, including grey on wash, measures at least 4.5:1. A new tint must be measured before it ships.

## Typography

**Display Font:** Archivo, variable width axis (with sans-serif fallback), loaded through next/font.
**Body Font:** Archivo at normal width.

**Character:** One grotesque in two voices: condensed and bold where a printed form would set names and headings, regular width where it would be read. Figures are tabular across the whole page.

### Hierarchy
- **Display** (700, 36px phone to 46px, line-height 1, condensed 78%): the player's name on a profile.
- **Headline** (700, 30–32px phone to 40–42px, line-height 1.05, condensed 78%): page titles (Discover, Tournaments, a tournament, Coverage). The record figure in a summary line (28px) uses the same voice.
- **Title** (700, 15px, condensed 80%, form green): section headings, set over a green hairline. Round headings in a draw are ink, 16px, condensed 80%.
- **Body** (400, 15px, line-height 1.45, tabular figures): result rows, meta lines, prose. Result rows sit at 14–15px.
- **Label** (400, 12–13px, pencil grey): context lines above a result, source notes, pager counts, section actions (always back at normal width).
- **Mark** (700, 12px, tabular): the letters inside W/L squares and result badges.

### Named Rules
**The Two Widths Rule.** Condensed width is for names and headings only; anything read as a sentence returns to 100% width, including the action text that sits beside a section heading.

**The Sentence Case Rule.** Headings and labels are sentence case at normal tracking. Federation codes (IND, CHN) are data and keep their capitals with slight tracking (0.04em); nothing else is uppercased or letter-spaced.

## Layout

One centred column, maximum 1240px, with 16px gutters on a phone and 32px from 640px. Profile, Discover, tournament and tournament-list pages are a main column plus a narrow side column (17–20rem, or a 15rem filter column on the left for Tournaments) separated by a 48px gap, stacking to one column below 1024px.

A sticky top bar (56px) carries the wordmark, a dominant player search (up to 520px) and the section links. Below 1024px the section links move to a three-tab bar fixed to the bottom of the screen (56px tabs, icons above labels, safe-area padding), and the page reserves bottom space for it.

Results are lists of ruled rows (8px vertical padding, hairline beneath). Each row is winner first, "d.", the other side, then the games in fixed 3.25rem columns, so a round lines up like a ruled sheet; from 640px a third game column is always reserved. Draw rounds use sticky round headings beneath the top bar. Every page ends with a footer line naming the sources and linking to Coverage.

**The Summary Line Rule.** A profile's facts sit in one line between a 2px form-green rule above and a hairline below: record, win rate of decided matches, tournaments, last-ten W/L marks. Never as tiles.

## Elevation & Depth

Flat. There are no shadows anywhere in the system. Depth is conveyed only by rules (form green for section structure, hairline for rows, sheet rule inside score cells) and by the wash tint on an opened or hovered row. The sticky top bar and sticky round headings use paper at 95% opacity with a light backdrop blur so content does not collide with them; that is the only layering effect.

**The Ruled Not Raised Rule.** If something needs separating, draw a line under it. Never lift it onto a card or a shadow.

## Shapes

Nearly square. Marks, the GameSheet cell and status notes use a 3px corner, the smallest a printed square can soften to. Controls (search, selects, quiet buttons) use a 4.8px corner; the discipline tab group and filter items 6px. Rows, sections and the summary line have no container and so no corners at all. The one round form is the thin by-discipline share bar (6px tall, fully rounded).

## Components

### Buttons
- **Shape:** gently squared (4.8px).
- **Primary:** form green with white text, 48px tall, 24px side padding, semibold; used for the Search submit only. Hover drops to 90% opacity green.
- **Quiet:** paper with a control-edge ring, ink text, 36px tall (32px in the pager); hover washes the ground. Filters and pagination.
- **Focus:** every interactive element shows the ballpoint-blue 2px outline at 2px offset.

### Result marks (W / L)
- **Won:** a 22px square, form-green fill, white W.
- **Lost:** a 22px square, paper ground, loss-red L, 1px loss-red inset ring.
- **Neutral (result badge):** pencil-grey text, hairline ring; walkovers and undecided results.
- A form strip lists the last ten decided results oldest to newest, with a written aria label of the count won.

### GameSheet (signature)
The scoresheet cell: a two-row grid with one 28px ruled column per game actually played, sheet-rule borders, 3px corner, 13px tabular figures. The winning score in each game is bold ink, the losing one pencil grey; when the top row is the viewed player, that row is ballpoint blue. It appears inside an opened result row beside the two sides' names.

### Result row (expandable)
Names stay ordinary links (withheld people are grey italic and never linked). The score is a separate button (at least 40px tall) with a chevron that rotates 90° over 150ms and opens the scoresheet beneath, tinting the row wash. A status the scores cannot show is a **status note**: wash ground, 12px ink text, 3px corner.

### Inputs / Fields
- **Style:** paper ground, 1px control-edge border, 4.8px corner, 36px tall (48px and 17px text for the Discover search), pencil-grey placeholder and leading search icon; the compact search shows a "/" key hint.
- **Hover:** border darkens toward ink at 40%.
- **Selects:** native select in the same control style with a pencil-grey chevron.

### Navigation
- **Bar:** 14px links, pencil grey, current section semibold ink with `aria-current`.
- **Phone tabs:** three equal tabs fixed at the bottom, 56px tall, 20px icon over 12px label; the current tab's icon turns form green.
- **Discipline tabs:** a joined row of condensed 14px semibold codes with match counts, control-edge borders, 40px tall; the current tab is filled form green with white text.

### Section
A green condensed 15px heading over a 1px form-green rule, with an optional normal-width pencil-grey action on the right. This is the only sectioning device.

### Source note
A quiet 12px line, "Source · [source] · About this data", on every page that shows records.

## Do's and Don'ts

### Do:
- **Do** separate content with rules: a 1px form-green rule under every section heading, hairlines between rows, a 2px green rule above the summary line.
- **Do** set every figure in tabular numerals and every game score in its own fixed column.
- **Do** keep ballpoint blue for the viewed player's scores and the focus ring only.
- **Do** write results as letters and statuses as words; colour reinforces, never replaces.
- **Do** mark absent data in words ("Not recorded", "Score unavailable", "No decided final is published for this event") and show provenance on every page.
- **Do** keep every text pair at 4.5:1 or above, touch targets at 44px, and transitions off under reduced motion.

### Don't:
- **Don't** use cards, rounded panels or shadows as page structure.
- **Don't** build hero banners, stat tiles or KPI boxes; facts go in the summary line.
- **Don't** put eyebrow labels or kickers over headings.
- **Don't** use uppercase, letter-spaced labels (federation codes are data, not labels).
- **Don't** add decorative court graphics, player photos or illustrations.
- **Don't** use filled colour badge chips for categories or metadata. The filled W square and the wash status note are scoresheet marks, not chips.
- **Don't** show a number the sources did not publish: no rankings, ratings, ages or live scores.
- **Don't** use red anywhere but an L mark or a written loss status.
