# BWF historical compilation: import record

Source `bwf_historical_compilation`: BWF elite results 2007 to July 2026, compiled by a third
party. **Not a live BWF connection**: the direct Fansite provider (`bwf`) is tracked separately and
stays `pending_access` (docs/bwf-access-request.md).

## Provenance

| Item | Value |
|---|---|
| Original data | Badminton World Federation tournament results |
| Compiled by | Sahil Motyar |
| Repository | https://github.com/SahilMotyar/bwf-match-data |
| Version | commit `0a6899162bf4b9639b76dcdbc0dca4c5d4800664` (2026-07-14) |
| Authorisation | Owner attestation, Leo Xu, 2026-11-14: the compiler granted use and redistribution. BWF authorised all uses (2026-11-12). The written grant was not supplied or verified (docs/data-sources.md) |
| Imported | 2026-11-14, `scout import-compilation <checkout>` (one `ingest_run` per run) |
| Stored | each match a revisioned raw record, keyed without the score (ADR-0005); the files stay outside git (`.tools/datasets/`) |

SHA-256 of the imported files:

| File | SHA-256 |
|---|---|
| matches.csv (105,147 rows) | `1bde0fec9329976d693b29ad3ccd888e4e2e4553cd65c5afc50a6442ad84b8ea` |
| index.json (4,029 tournaments) | `3c4ef3df4bfb038a3429a4f15050a44f3ea2bcd2a0ffabeb472d9d3029476ffa` |
| ms.csv | `983d6127026819fa89cb463da7ac45b88d153199fdbff2533c19b5cbc3122000` |
| ws.csv | `e29f01b5e8f21c645f8377e28441c6135c1fb7dfb094fe281f1953ab9bd6a9cf` |
| md.csv | `0a899ede9ccd05a48260b512af7b4a994944468062c85651ead2f29d177837c4` |
| wd.csv | `123f6cb560c1072beae51709ade9270cbafb9f212a7c877343655251af6a560e` |
| xd.csv | `5551d74186761525f8007721036dcf6c69ef07bfece89471cef0ccbceccb1d03` |

`matches.csv` is the five discipline files combined (28,270 + 21,372 + 19,693 + 16,376 + 19,436).

## How rows become records (`backend/src/scout/ingest/bwf_compilation.py`)

- **Tournament:** the index entry with the same name whose dates contain the match date. That
  entry carries BWF's own tournament id. If no single entry fits, the row is quarantined
  (`unknown_tournament`).
- **Match key:** tournament id, event, round, date and both sides; never the score.
  - Identical repeats are stored once (`duplicate_rows`).
  - Repeats that differ are quarantined (`key_collision`).
- **Players:** the exact name within the dataset (`name:<name>`), or the BWF id the compiler
  appended as `[id]` (`bwf:<id>`). They are never linked to another source by name
  (ADR-0003, ADR-0011).
- **Status:** read from the scoring format, never from the winner alone.
  - **Completed:** the winner took the games needed (2 of 3 at 21 points; 3 of 5 in the 5x11
    trial), the match stopped at that point, and every game ended legally.
  - **Retired:** the match stopped short, inside a game or between games.
  - **Quarantined (`irregular_score`):** anything that contradicts the winner.
- **Events:** each discipline, with qualification as its own event ("MS Qualification").

## Results (import of 2026-11-14, verified against the database)

| | Count |
|---|---|
| Source rows (matches.csv) | 105,147 |
| Exact duplicate rows merged (the README's 208 blank-round repeats) | 208 |
| Unique match records stored | 104,939 (104,939 + 208 = 105,147) |
| Normalised matches | **104,837**: completed 103,380 · retired 1,457 |
| Quarantined (`ingest_issue`) | 102 `irregular_score` (games that contradict the recorded winner) |
| Unresolved tournaments | 0 (the 18 repeated names resolved by date) |
| Tournaments | **577**, 2007-01-16 to 2026-07-05, each with BWF's index id |
| Source players | **9,251** (the README's 9,251 distinct names); 24 keyed by BWF id |
| Players linked to any other source | 0 (no name-based merging) |
| Same event already held by another source | 0 found |
| By discipline | MS 28,181 · WS 21,297 · MD 19,643 · WD 16,335 · XD 19,381 |
| Qualification matches | 15,505 |

**Rating readiness:**
- **Eligible:** 103,380 matches are completed with a full legal score and both sides identified.
  The 1,457 retirements are kept but are not rating-eligible.
- **Players by completed matches:** 1,447 with 50+, 994 with 20–49, 1,158 with 10–19, 1,556 with
  5–9, and 4,079 with 1–4.
- **Identity uncertainty:** players are names within this dataset. A name change or two people
  sharing one name is resolved only where the compiler added a `[id]`.
- **Data has a date, not a time:** matches on the same day are ordered by id, so chronological
  backtests need a stable intra-day order.
