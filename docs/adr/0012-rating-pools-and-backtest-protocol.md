# ADR-0012: Rating pools, ordering and the M8 backtest protocol

Status: Accepted 2026-11-14 (pre-registration: committed before any model was run on real data).
Amends ADR-0006.

## Context
M8 tests whether Mynton can estimate player strength and predict singles results. ADR-0006 fixed
the main rules: pre-match predictions only, chronological splits, log loss first, and leakage tests.
The data now has properties ADR-0006 did not settle:
- **Dates without times.** 29% of a player's match days hold more than one singles match.
- **Unlinked identities.** BWF compilation players are names within that dataset, and no BWF player
  is linked to a federation player (ADR-0003, ADR-0011).
- **Separate competitive worlds.** Domestic pools that never meet.

This ADR fixes those choices now, so they cannot be tuned against results.

## Decision

### Pools (never combined)
| Pool | Source | Players |
|---|---|---|
| `bwf:MS`, `bwf:WS` | `bwf_historical_compilation` | source players, as the compilation names them |
| `fed:MS`, `fed:WS` | all `tournamentsoftware*` sources | canonical players (Tier A links only) |

- **Juniors** (`fed:*` events that `privacy.is_adult_event` does not recognise as adult, with a
  known discipline) form separate `fed:MS:junior` and `fed:WS:junior` pools.
- **Para events** are excluded.
- **No cross-family predictions.** A BWF and a federation player are never compared: the result is
  "incompatible pools".

### Connectivity
A prediction is made only when both players are in the same connected component of the opponent
graph built from matches **before** that match. Otherwise the outcome is an abstention
(`incompatible_pools`, or `insufficient_data` for a player with no prior eligible match).

Every model is scored on the same matches. Abstentions are counted and reported as coverage, never
dropped silently.

### Eligible outcomes
- **Scored:** `completed` matches with a winner, exactly one player per side, a classified singles
  discipline, and no withheld player.
- **Not scored and no rating update:** `walkover`, `not_played`, `winner_only`, `disqualified`.
- **Retired:** neither, by default. A sensitivity run counts them as results.
- **The BWF identity audit:** players it flags (impossible schedules) are reported; their matches
  are kept in the primary run, and a sensitivity run without them is reported too.

### Ordering and same-day batching
Matches are ordered by date, then by tournament, then by round rank:
1. qualification before the main draw;
2. in the main draw, larger rounds first (R128 → … → Final);
3. "Round N" ascending;
4. group and pool stages before knockouts.

Matches with the same date and round rank form a **batch**. Every match in a batch is predicted
from the state before the batch; the batch's results are then applied together.

A match without a round label joins a **day batch**: it is predicted from the state at the start of
the day and applied after every labelled match of that day.

Day-only batching (one batch per date) is a configuration option, compared on validation only.

### Splits (fixed before evaluation)
| Family | Train (and warm-up) | Validation | Test (read once) |
|---|---|---|---|
| BWF | 2007-01-01 → 2021-12-31 | 2022-01-01 → 2024-12-31 | 2025-01-01 → 2026-07-05 |
| Federations | start → 2025-06-30 | 2025-07-01 → 2025-12-31 | 2026-01-01 → end of data |

- Ratings run continuously from the first match. A split only decides which predictions are scored.
- **Tuning** (K, provisional K and its match count, inactivity decay, Glicko-2 τ and rating
  period, batching) minimises validation log loss.
- **The test split is evaluated once,** with the selected configurations, and the result is
  reported whatever it is.
- The federation family has under three years of history, so its results are secondary.

### Models and baselines (ADR-0006's list, revised)
1. Constant 0.5.
2. Prior win rate, Beta(2, 2)-smoothed and combined by log5.
3. Elo with default K = 32, initial rating 1500, and the standard logistic expectation.
4. Tuned Elo.
5. Glicko-2 (Glickman 2012), with a tuned τ and rating period.

ADR-0006's home-advantage baseline is **dropped**: matches carry no venue country and players no
nationality, so it cannot be computed.

No margin, prestige, age, country or form term is added unless it improves validation log loss,
and none is in the first round.

### Metrics
- **Primary:** log loss.
- **Also:** Brier score, accuracy, and calibration (reliability table in deciles, expected
  calibration error).
- **Confidence intervals:** 95% bootstrap intervals, resampling whole tournaments (seeded, 1,000
  resamples). A model "beats" a baseline only if the paired bootstrap interval of the log-loss
  difference excludes 0.
- **Reported for:** coverage; provisional players (< 10 prior matches) and established players
  (≥ 10); each discipline; and each year.

### Public use
No probability is shown to users until the report recommends it and the owner approves.

## Consequences
- Derived tables are versioned (model, configuration, snapshot, run). Match data is never changed.
- A rebuild replays from a snapshot; an incremental rebuild must equal a full one.
