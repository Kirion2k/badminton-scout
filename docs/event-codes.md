# Event codes (evidence for `backend/src/scout/ingest/event_codes.py`)

Tournament Software portals name events with short codes in the federation's language. The same
code can mean different things in different languages, so a code is read only in the language of
the tournament it belongs to, and only when it fits the draw (one player per side for singles).
Anything unclear stays unclassified: an unknown discipline costs coverage, but a wrong one
corrupts statistics.

## The conflicts that decide the design

Evidence: on 2026-11-14, each player was labelled by the other events they played (men's events
HE/HD/JE/JD/MS/BS/BD, women's events DE/DD/ME/WS/WD/GS). Then each side of a GD or MD match
was checked for that mix. Counts are match sides. Only aggregates were inspected, never names.

| Code | Source | Tournament codes | Sides: man and woman | Two women | Two men | Reading |
|---|---|---|---|---|---|---|
| GD | dbv | German (HE/DE/…) | 2,023 | 0 | 0 | mixed doubles (Gemischtes Doppel) |
| GD | badvla | German or Dutch | 3,737 | 3 | 0 | mixed doubles (gemengd dubbel) |
| GD | dbv | English (MS/WS/…) | 0 | 65 | 0 | girls' doubles |
| MD | dbv | German, or junior-only | 0 | 3,127 | 0 | girls' doubles (Mädchendoppel) |
| MD | dbv, badvla, obv | English | 0 | 0 | 1,358 | men's doubles |
| MD | obv | German | 54 | 18 (other) | 0 | **conflicting: left unclassified** |
| MD | badvla | German or Dutch | 0 | 24 | 0 | too little evidence: left unclassified |

Before this change every source was read with English codes, so stored German and Flemish mixed
doubles were labelled women's doubles, and German girls' doubles were labelled men's doubles.
`scout events reclassify` corrected them on 2026-11-14:

| Change | Matches |
|---|---|
| badvla women's doubles → mixed | 2,177 |
| dbv women's doubles → mixed | 1,361 |
| dbv men's doubles → women's doubles (girls) | 1,821 |
| obv and badvla MD → unclassified | 43 |

## Tables

- **English** (every source; also Canada, Australia, New Zealand, Scotland, England):
  MS, WS, MD, WD, XD, MX, MXD; junior BS, GS, BD, GD (GD = girls' doubles). Australia's grade
  prefix reads AMS, BMS, …, OMS, DXD as grade plus event.
- **German** (dbv, obv): HE MS, DE WS, HD MD, DD WD, GD/MX/MIX/MIXED XD; junior JE MS, ME WS,
  JD MD, MD WD (dbv only); also Herreneinzel, Dameneinzel, Herrendoppel, Damendoppel.
- **Dutch and French, Flanders** (badvla): HE, DE, HD, DD, GD as in German; SM MS, SD WS, DM MD,
  DX/DMX XD; JE and ME junior; "Simples Filles" and "Simple Garçons" junior; "Double Mixte" XD.
- **Portuguese, Brazil** (cbbd): SM MS, SF WS, DM MD, DF WD, DX XD, with grade suffixes (SMB, SFA)
  and age groups (Sub17, Juvenil, Infanto, Infantil).
- **Indonesian** (global source): TPA MS, TPI WS, GPA MD, GPI WD; TAPA, TAPI, GAPA, GAPI are
  children's events, so junior. TRA, GRA, GRC, UDPA, UDPI and TTA are not understood: unclassified.
- **Unambiguous English codes** (MS, WS, WD, XD, BS, GS, BD) are also read in German and Flemish
  tournaments, which mix them in. GD and MD are not, because they are the conflicting codes.
- **English words** ("Men's Singles") are read in every source. In German, Dutch and Portuguese
  sources this happens only when the name holds no English code.

## Language of a tournament
A dbv, obv or badvla tournament whose events use English codes (MS, WS, WD, XD, BS, GS, BD) and
none of the German or Dutch ones (HE, DE, HD, DD, JE, ME, JD) is read as English. Otherwise it is
read in the source's language.

## Category
Each event is also classified as adult, junior or para (`event.category`).
- **Para:** para classes (WH1, SL3, SU5, SH6), "para", wheelchair in any language.
- **Junior:** age bands (U13, Sub17, Yr 11), boys/girls words in any language, the junior codes
  above, and age-group prefixes (CAD, BEN, JUV, PEE, Juvenil, Infanto, Schüler).
- **Adult:** everything else, including masters (O35, 35+).

Rating pools never mix the three (ADR-0012).

## Results (2026-11-14)
Federation matches without a discipline fell from 155,747 to 30,714 (of 328,848). Categories:
adult 216,368, junior 110,601, para 1,532. Not yet understood:
- singles or doubles without a gender ("Week 4 Singles", "Box Doubles");
- Indonesian codes nobody here can read with confidence;
- "OS" and "OD" (England).
