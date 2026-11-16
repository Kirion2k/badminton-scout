# Curating BWF fixtures (source `bwf_curated`, ADR-0014)

**The bridge:** a person enters upcoming BWF singles fixtures and their results from
`bwfbadminton.com`, so Mynton can record forecasts before play and score them after. This lasts
until BWF provides a feed.
- **Keep the CSV outside the repository.** It is third-party data.
- **Read the pages as any visitor would.** No scripts, and never past a challenge.

## The CSV
One row per match, with a header. Re-importing the same file is harmless: a row that has not
changed is not stored again.

| Column | Value |
|---|---|
| `fixture_key` | Stable per match: the BWF match id if the page shows one, otherwise `tournament-draw-round-match number` |
| `tournament_key`, `tournament_name` | The BWF tournament id from the URL, and its name |
| `discipline` | `MS` or `WS` |
| `round` | e.g. `R32`, `QF` (optional) |
| `scheduled_date` | Local date, `YYYY-MM-DD` |
| `scheduled_start` | Local start time `HH:MM`, only if the order of play gives one. Leave it empty for "not before" or "follows" times |
| `timezone` | The venue's IANA zone, e.g. `Asia/Tokyo`, `Europe/Copenhagen` |
| `status` | `scheduled`, `postponed`, `live`, `completed`, `walkover`, `retired`, `abandoned`, `cancelled` |
| `player_a_bwf_id`, `player_b_bwf_id` | The number in the player's BWF profile URL. **Required:** a name alone is never enough |
| `player_a_name`, `player_b_name` | As shown |
| `winner` | `A`, `B` or empty. Required for `completed`; allowed for `retired` and `walkover` |
| `score` | Games, e.g. `21-15 18-21 21-19` (optional) |
| `checked_at` | When you looked, with a UTC offset, e.g. `2026-11-20T08:15:00+00:00` |

## Daily routine
1. **Before each day's play,** update the rows from the order of play: times, status and player
   changes. Then:

   ```
   scout fixtures import ~/mynton-fixtures/2026-11.csv
   ```

   - This issues a forecast for every eligible fixture.
   - Forecasts close 30 minutes before a known start, or at local midnight for a date only.
   - Fixture data older than 24 hours is never forecast, so re-check it the same day.
2. **Link new players once:**
   - `scout fixtures unresolved` lists them;
   - check each BWF profile against the player's Mynton history (results, nationality);
   - then run `scout identity link-fixture-player --source-player N --to-player M --reason "…"`.

   If you are unsure, do not link: the fixture simply gets no forecast. A link can be undone with
   `scout identity undo`.
3. **After play,** enter results (`status`, `winner`, `score`) and import again.
4. **A second person verifies each result** against the BWF page with
   `scout fixtures verify-result <fixture id>`.
   - Only verified results count.
   - The person who entered a result cannot verify it.
   - Correcting a result needs verifying again.
   - A verified result that later changes is reported as a conflict and never scored.
5. **Check the pipeline** with `scout fixtures status` (missed fixtures and why, failures) and
   `scout fixtures pilot` (the operational pilot report).
