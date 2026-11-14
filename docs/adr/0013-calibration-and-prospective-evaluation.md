# ADR-0013: BWF singles calibration, prospective evaluation and the matchup flags

Status: Accepted 2026-11-15. Pre-registration: committed before any calibration was fitted.
Builds on ADR-0006 and ADR-0012.

## Context
M8 found that BWF singles Glicko-2 forecasts carry real skill, but the 0.5–0.7 range is about 5
points too confident (docs/research/m8-rating-feasibility.md). The 2025-01-01 → 2026-07-05 test
period has been read twice, so it cannot be fresh evidence for anything fitted now. The BWF
archive ends 2026-07-05. No newer authorised BWF results exist, and none may be invented.

## Decision

### What stays frozen
- **The Glicko-2 configuration** selected in M8 (`docs/research/m8-bwf-selected.json`: τ 1.2,
  3-day periods, RD₀ 250) on snapshot 1. Its parameters are never re-tuned against 2025–2026.
- **M8's result files** are kept as they are. M8.1 writes new `m8.1-*` files.

### Calibration (fitted on development data only)
- **Inputs:** the stored pre-match Glicko-2 predictions of that configuration, as log-odds
  `z = logit(p)`. A model's z is antisymmetric: swapping the players negates it.
- **Development data:** predictions dated 2012-01-01 → 2024-12-31. 2007–2011 is warm-up, when most
  ratings are immature.
- **2025-01-01 onwards** is **never read** by the fitter: a code guard, plus a test.

**Candidates.** None has an intercept and all are odd in z, so `P(A beats B) + P(B beats A) = 1`,
and player order cannot change a matchup:
1. **Uncalibrated:** `σ(z)`.
2. **Temperature (primary):** `σ(z / T)`, with `T > 0`.
3. **Experience-dependent temperature:** `σ(z / T_e)`, with one temperature when both players are
   established (≥10 prior matches) and one otherwise. The established flag is symmetric in the
   two players.

No manual offsets, no orientation-dependent term, and no per-discipline fitting in this round.

**Fitting and folds:**
- **Fit:** minimise mean log loss with a bounded golden-section search, T in [0.25, 4]. Deterministic.
- **Folds:** rolling origin by calendar year, 2016 to 2024. For each fold year Y, fit on dev years
  2012..Y−1 and evaluate on Y.
- **Selection:** temperature is chosen unless candidate 3's mean fold log-loss improvement over
  temperature has a 95% bootstrap interval (resampling fold-year tournaments) entirely below 0.
  Uncalibrated is chosen only if temperature does not improve on it in the same sense.
- **Final parameters:** refitted on all of 2012–2024.

**Reporting:**
- **Per candidate:** log loss, Brier, ECE, reliability bins with counts, by MS/WS and by
  established vs provisional, plus the fitted T per fold.
- **The 2025–2026 period** may be shown only as **"previously examined: diagnostic only"**, never
  as evidence for release.

### Prospective evaluation (the only release evidence)
- **Recording:** a forecast is recorded before its match is played, in `issued_prediction`. It
  stores the issue time, scheduled date, external match reference, players, discipline,
  probability, model configuration hash, calibration hash, rating run and snapshot.
- **Immutability:**
  - a database trigger forbids changing or deleting a recorded forecast;
  - the result may be filled once.
- **Who can issue:** only for matchups the decision rules would give a probability (ignoring the
  public flag), scheduled after the snapshot's last match day.
- **Resolving:** forecasts are scored only against verified results from an authorised source,
  imported normally.

### Release conditions for public BWF singles probabilities
Precision targets are derived from M8's variance, not tuned to pass. All of these must hold on
resolved prospective forecasts:
1. **At least 1,000 resolved forecasts.** That gives a log-loss interval of roughly ±0.02 (M8:
   n = 4,313 gave ±0.016).
2. **Beats the win rate:** calibrated log loss beats the win-rate baseline on the same matches,
   with a 95% cluster-bootstrap interval entirely below 0.
3. **Calibration error:** the 95% upper bound of ECE is ≤ 0.04.
4. **Reliability:** every reliability bin with ≥ 200 forecasts contains the observed rate in its
   95% interval. Bins with fewer forecasts are reported, not judged.
5. **Sign-off:** an independent review of the evaluation code and data, and the owner's approval.

Until all hold, `matchups.PUBLIC_PROBABILITIES` stays `False`. Missing evidence is never a reason
to lower these conditions.

### The flags
`PUBLIC_PROBABILITIES` and `PUBLIC_RATINGS` are code constants in `scout/matchups.py`, both
`False`.
- Turning one on is a reviewed commit, as for `privacy.PUBLISH_RESTRICTED_EVENTS`.
- `PUBLIC_RATINGS` only allows showing BWF singles rating numbers, labelled as Mynton estimates and
  not BWF rankings.

### Junior and federation ratings
- No route serves a federation or junior rating, ranking or probability.
- Rating tables are read only by offline commands with direct database access.
- The matchup decision never reads a `fed:*` or junior run.
