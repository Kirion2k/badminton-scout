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

## Results

See the import report at the end of this file (filled in from the database after the run).
