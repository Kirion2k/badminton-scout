# ADR-0006: Singles Elo, and how its predictive value is evaluated

Status: Accepted 2026-11-12 · Implemented in M8. Amended by ADR-0012 (pools, ordering, splits, baselines)

## Decision
Elo, computed separately per singles discipline (MS, WS), is the first performance model. Beating a constant 0.5 forecast is necessary but not sufficient evidence that it works.

### Two separate outputs
- **Retrospective rating:** a player's rating *after* a match, for charts and profiles. It uses that match's result, so it is never a prediction.
- **Pre-match prediction:** `P(A beats B)` computed only from matches that finished strictly before this one. Ordering is by date, then by round within a tournament, so same-day earlier rounds count and the match itself never does. These are stored separately and only these are ever scored.

### Evaluation protocol
- **Chronological splits only.** Fit and tune on the earliest period, select on a validation period, report once on a held-out test period. Then a rolling-origin check: refit yearly and predict the next year. No random splits.
- **Baselines Elo must beat:**
  1. constant 0.5
  2. prior win rate (smoothed with a Beta prior), pre-match
  3. home-advantage-only
  4. Elo with default K (to show that tuning helped)
- **Metrics:** log loss (primary), Brier score, accuracy (secondary), and calibration: a reliability table in deciles plus expected calibration error. Each comes with bootstrap confidence intervals. Results are also stratified by tier and by experience (players with < 10 prior matches reported separately).
- **Leakage checks as tests:**
  - every feature timestamp < match timestamp
  - the test period is never read during tuning
  - shuffling the order of outcomes destroys the skill
  - the ratings table used for prediction contains no row from the match being predicted

## Constraint
Evaluation on real matches needs a source with at least `LOCAL_RESEARCH` evidence (ADR-0002). Until then, only the code and the leakage tests are built, against synthetic data. Synthetic results say nothing about real predictive skill and won't be reported as if they did.
