# Spec: `GET /v1/matchups/compare` (designed in M8, not published)

**Status:** contract only. The response models live in `backend/src/scout/matchups.py`, with
tests. **No route is mounted**: a test asserts `/v1/matchups/compare` returns 404. Publishing
needs the owner's approval of `docs/research/m8-rating-feasibility.md`.

## Request
`GET /v1/matchups/compare?a=<player id>&b=<player id>&discipline=MS|WS`

Merged ids redirect to the canonical pair (308), as head-to-head does. Doubles are not offered:
doubles models are offline research only.

## Response: one of five outcomes
| `outcome` | When | Carries |
|---|---|---|
| `probability` | Both players are in the same validated pool and connected through earlier matches; neither is provisional; the pool's model passed its held-out test | `probability_a`, the model, both players' evidence, and the calibration bin the forecast falls in (how such forecasts did in the test period) |
| `comparison` | Same pool and connected, but no validated probability (e.g. a provisional player) | Both ratings and match counts, with no percentage. `reasons` says why |
| `insufficient_data` | A player has no eligible match in the discipline | `reasons` |
| `incompatible_pools` | No chain of played matches connects them: different federations, BWF vs a federation, or separate islands within one | `reasons` naming the pools |
| `identity_uncertain` | A player's record is flagged by the identity audit (e.g. twice in one knockout round) | `reasons` |

The model's validator enforces the rules. A probability exists exactly when `outcome` is
`probability`, and then it carries its model, evidence and calibration. Ratings from two pools
are never compared. A provisional player never gets a probability. Every other outcome says why.

## Evidence on every rated player
`pool`, `rating`, `rating_deviation` (Glicko-2), `prior_matches`, `provisional` (under 10),
`last_played`.

## Model and freshness
`model`: name, version (the configuration hash), run, snapshot, `data_as_of` (the last match day
in the snapshot) and `computed_at`. Ratings come only from a stored run (`rating_run`), never
computed per request. A historical correction triggers a rebuild: a full replay by default.
Incremental rebuilds are tested to be identical.

## Not in this contract
- Leaderboards or rankings.
- Cross-federation or BWF-vs-federation percentages.
- Doubles.
- Any margin, prestige or form adjustment not validated in a backtest.
