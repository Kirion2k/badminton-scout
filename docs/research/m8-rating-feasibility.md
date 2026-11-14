# M8: Can Mynton estimate strength and predict matchups?

2026-11-14. Protocol: ADR-0012, pre-registered in `e48537f` before any model touched real data.
Selections were committed before each test split was read:
- BWF singles: `7c6d7f3`
- doubles: `92edb51`
- federations: `3e7cada`

Each test split was evaluated once. Raw results are in `docs/research/m8-*-results.json` and
`m8-audit.json`. Every figure below comes from those runs, reproducible with
`scout ratings snapshot | tune | evaluate | audit`.

## Decision

- **No public win probabilities yet.**
- **BWF singles is one step away:** a limited, owner-approved release is justified after one fix
  (recalibration, below).
- **Federation predictions are not ready.**
- **Doubles stays research.**

| Pool | Beats baselines (95% CI) | Calibrated | Coverage of test matches | Verdict |
|---|---|---|---|---|
| BWF MS/WS | yes, clearly | mostly (ECE 0.02; 0.5–0.7 too confident) | 95% | **conditional go:** established players, after recalibration and owner approval |
| Federation MS/WS (adult, junior) | yes, modestly (tuned only) | no (ECE 0.03–0.04, extremes off by up to 7 points) | 55% | **no-go:** show ratings-free comparisons only |
| BWF doubles | yes, clearly (TrueSkill) | yes (ECE 0.015) | 92% | **research only** (as instructed) |
| BWF vs federation, or across federations | n/a: no connecting matches | n/a | 0% | **never:** `incompatible_pools` |

## 1. Rating-ready data

Figures on 2026-11-14. Reported figures were reconciled first: the database had moved from
358,839 to 401,934 matches at the start and 439,450 at the end, because syncs kept running.

| | BWF compilation | Federations (Tournament Software) |
|---|---|---|
| Eligible singles matches | 48,607 (MS 27,657 · WS 20,950) | 139,203 (MS 53,561 · WS 19,257 · junior MS 42,101 · junior WS 24,284) |
| Excluded | retired 871 | unclassified event 30,841 · walkover 7,909 · uncategorised 852 · not played 800 · retired 722 · para 264 · winner-only 91 · disqualified 22 |
| Players (any eligible match) | MS 2,991 · WS 1,845 | MS 19,999 · WS 7,763 · junior 19,126 / 10,558 |
| Players with ≥10 matches | MS 739 · WS 562 | MS 2,576 · WS 817 · junior 1,620 / 925 |
| … and active since 2025 | MS 213 · WS 164 | MS 2,427 · WS 760 · junior 1,594 / 910 |
| Span | 2007-01 → 2026-07-05 (archive, not updated) | 2023-02 → 2026-11 (live) |

Notes on the data:
- **Side order.** Side 1 won 50.8% of BWF matches, so side order carries no signal there. In
  federation data side 1 won 53–58%, probably seeding or draw position (§10).
- **Same-day ordering.** No match has a time, and 29% of a player's match days hold several
  matches. Matches are ordered by date, then round: all 148 observed round labels are ranked.
  Matches in the same round are predicted together from the state before it.

## 2. Data quality and identity limits

- **Event classification fixed.** Codes were read as English everywhere. 3,538 German and Flemish
  mixed-doubles matches were stored as women's doubles, and 1,821 German girls' doubles as men's
  doubles. Corrected (`docs/event-codes.md`), and unclassified federation matches fell from
  155,747 to 30,714.
- **BWF identities are names.** The audit flags 5 of 9,251 players appearing twice in one knockout
  round (two people under one name). 0 played two tournaments on one day, and 0 appear in both
  MS and WS.
  - Removing the flagged players changed no test metric: they had no test-period matches.
  - The reverse error (one person under two spellings) cannot be detected without BWF player ids.
- **No cross-source duplicates.** 0 of 91,268 federation singles in the BWF period match a BWF
  record on discipline, both names and date. Pools never mix anyway.
- **Withheld players** are excluded (0 today). **Para events** are excluded (264). **Juniors** are
  rated only among juniors.
- **No automatic merges** were made or proposed (ADR-0003, ADR-0011).

## 3. Results: BWF singles (test 2025-01-01 → 2026-07-05; 4,529 matches)

| Model | Log loss (95% CI) | Brier | Accuracy | ECE | Predicted |
|---|---|---|---|---|---|
| Constant 0.5 | 0.693 | 0.250 | 50.0% | – | 4,353 |
| Win rate (Beta-smoothed, log5) | 0.611 (0.600–0.621) | 0.211 | 66.7% | 0.045 | 4,313 |
| Elo, default (K 32) | 0.562 (0.545–0.578) | 0.192 | 70.3% | 0.024 | 4,353 |
| Elo, tuned (K 32; K 96 for a player's first 20 matches) | 0.550 (0.533–0.565) | 0.187 | 71.0% | 0.019 | 4,313 |
| Glicko-2 (3-day periods, τ insensitive, RD₀ 250) | **0.548** (0.531–0.563) | **0.186** | **71.1%** | 0.021 | 4,313 |

Paired log-loss differences, with 95% cluster-bootstrap intervals over the same matches. Below
zero favours the first model:

| Comparison | Difference | Significant? |
|---|---|---|
| Glicko-2 − win rate | −0.063 (−0.071 to −0.054) | yes |
| Glicko-2 − default Elo | −0.013 (−0.020 to −0.008) | yes |
| Tuned Elo − default Elo | −0.012 (−0.017 to −0.007) | yes: tuning helped |
| **Glicko-2 − tuned Elo** | **−0.002 (−0.005 to +0.002)** | **no: a tie** |

- **Established vs provisional** (Glicko-2):
  - established (both players ≥10 prior matches, 3,620 matches): 0.546, ECE 0.020;
  - provisional (693 matches): 0.559, ECE 0.043.
- **By discipline:** WS is easier (0.498) than MS (0.591).
- **Over time:** 2025 0.544, 2026 0.558; validation years 0.540–0.546. Stable.
- **Calibration (Glicko-2):** close at the extremes. The 0.5–0.7 forecasts are too confident:
  - 0.6–0.7 bin: forecast 0.649, observed 0.589 (n = 555);
  - 0.5–0.6 bin: forecast 0.548, observed 0.505.
- **Sensitivities:**
  - counting retirements as results: Glicko-2 0.552;
  - without the 5 identity-flagged players: unchanged;
  - replays are deterministic (identical output hashes).
- **Not adopted, because validation rejected it:** inactivity decay (worse at every setting).
  Round-level vs day-level batching made no material difference.

## 4. Results: federations (test 2026-01-01 → 2026-11-08; 94,605 matches)

| Model | Log loss (95% CI) | Accuracy | ECE | Predicted |
|---|---|---|---|---|
| Constant | 0.693 | 50% | – | 52,440 |
| Win rate | 0.611 (0.604–0.618) | 65.2% | 0.037 | 52,440 |
| Elo, default | 0.635 (0.630–0.640): **worse than win rate** | 65.5% | 0.082 | 52,440 |
| Elo, tuned (K 64; K 192 for first 20) | 0.598 (0.588–0.608) | 66.9% | 0.042 | 52,440 |
| Glicko-2 (1-day periods) | 0.588 (0.576–0.599) | 67.8% | 0.026 | 35,912 |

- **Coverage is the problem.** 31% of test matches involve a player with no prior match, and 13%
  are between players with no chain of matches between them.
  - Glicko-2 covers fewer matches: its daily periods hide same-day earlier results.
  - On the 35,912 matches both predict, Glicko-2 beats tuned Elo by −0.009 (−0.014 to −0.004).
- **Established players are fine:**
  - Glicko-2 0.532 (n = 9,499);
  - tuned Elo 0.553 (n = 10,688).
- **Most predictions are provisional:**
  - tuned Elo 0.610 (n = 41,752), barely better than the win rate (0.618).
- **Calibration (tuned Elo) is poor at the low end:**
  - 0.0–0.1 bin: forecast 0.061, observed 0.132;
  - 0.1–0.2 bin: forecast 0.152, observed 0.252.
  The direction matches the side-1 effect above.

## 5. Doubles (BWF, research only; test 5,895 matches)

| Model | Log loss (95% CI) | Accuracy | ECE | New partnerships (385) |
|---|---|---|---|---|
| Constant | 0.693 | 50% | – | 0.693 |
| Pair Elo (K 64) | 0.568 (0.551–0.584) | 70.6% | 0.019 | 0.675 |
| Player-level team Elo (K 64) | 0.520 (0.505–0.535) | 74.2% | 0.013 | 0.536 |
| **TrueSkill, two teams** (β 25/3, τ 0.5) | **0.512** (0.497–0.526) | **74.5%** | 0.015 | **0.520** |

- **TrueSkill beats team Elo:** −0.008 (−0.011 to −0.006).
- **Player-level models beat pair Elo:** −0.048 to −0.057.
- **Partner changes:** pair-level models know nothing about a new partnership. Player-level models
  carry each player over, which is the decisive advantage.
- **By discipline:** WD is easiest (0.465), then XD (0.514), then MD (0.552).
- **Not done:** federation doubles. Doubles identities are weaker, and the singles backtest took
  priority.

## 6. Can pools be compared?

| Pool | Players | Components | Largest component | Comparable player pairs |
|---|---|---|---|---|
| BWF MS | 2,991 | 4 | 99.8% | 99.6% |
| BWF WS | 1,845 | 1 | 100% | 100% |
| Federation MS | 19,999 | 348 | 18% | 8% |
| Federation WS | 7,763 | 292 | 17% | 6% |
| Federation junior MS / WS | 19,126 / 10,558 | 324 / 309 | 14% / 17% | 5% / 5% |

- **Federations never meet.**
  - 0 matches join players from different home federations.
  - 0 players are shared between BWF and the federations: no verified identifier links them, and
    names are not used.
- **Within one federation, domestic circuits are connected:**

  | Federation | Players in the largest component |
  |---|---|
  | Germany | 98% |
  | Flanders | 99% |
  | Scotland | 99% |
  | Austria | 94% |
  | Australia | 94% |
  | New Zealand | 75% |

- **The global source and Brazil are islands:** 19% and 26%. 27% and 44% of their players are
  tournament-scoped records, which can never link to anyone.

## 7. Versioned architecture (built)

Derived tables only (migration 0023); match data is never changed:
- `rating_model`: configuration hash;
- `rating_snapshot` and `rating_snapshot_match`: eligible matches frozen with player ids and a
  content hash;
- `rating_run`: code version (git SHA), splits, metrics, output hash;
- `rating_point`: retrospective history;
- `match_prediction`: pre-match only, the only thing scored.

Rebuilds:
- **Full rebuild is the default.** A full BWF replay takes under a second.
- **Incremental rebuild** keeps predictions before the earliest changed day. Tests show it equals
  a full rebuild after a correction, an insertion, a removal and an identity merge. On real data
  (871 retirements added) the output hashes match.

## 8. Answers

1. **Players with enough history:**
   - BWF: 1,301 with ≥10 singles matches; 377 of them active since 2025.
   - Federations: 3,393 adults and 2,545 juniors with ≥10.
2. **Eligible completed matches:** 48,607 BWF singles; 139,203 federation singles; 54,773 BWF
   doubles.
3. **Best model:**
   - BWF singles: Glicko-2 and tuned Elo tie.
   - Federations: Glicko-2 on what it covers; tuned Elo covers more.
   - Doubles: TrueSkill.
   - The defaults are not good enough: default Elo loses to the win rate on federations.
4. **Calibration:**
   - BWF: good overall (ECE 0.02), mid-range forecasts about 5 points too confident.
   - Federations: poor at the extremes.
5. **Newer players:**
   - BWF provisional: 0.559 vs 0.546 established.
   - Federation provisional: barely better than the win rate.
   - Not reliable enough to show a probability.
6. **National pools:** not comparable with each other: zero connecting matches.
7. **BWF and domestic ratings:** cannot be combined. There are no verified identity links; 0
   shared players.
8. **Matchups without enough evidence:**
   - any cross-federation or BWF-vs-federation pair;
   - federation pairs in different islands (92% of player pairs);
   - any match with a newcomer (31% of federation test matches).
9. **Ready for public use?** Not yet (see Decision).
10. **Highest-leverage improvements:**
    - (a) **Recalibrate** on validation (temperature or Platt scaling), then re-test. This is the
      one fix BWF needs.
    - (b) **Test seeding and draw position** as a pre-match feature. Side 1 wins 53–58% in
      federations: it is real information, and it miscalibrates models that ignore it.
    - (c) **Stable identifiers:** BWF player ids (through approved access), and member ids for
      tournament-scoped federation records.
    - (d) **More federation history:** the backfill now works, with Australia back to Dec 2022
      and New Zealand to Dec 2021.
    - (e) **Same-day-aware Glicko-2,** to recover its lost coverage.
    - (f) **Test game-score margin.**

## 9. Public-use rules if the owner approves BWF singles

- **Pool:** within `bwf:MS` or `bwf:WS` only.
- **Players:** both players established (≥10 prior matches); recalibrated model.
- **Shown with the probability:** the calibration bin's track record, the model version, and "data
  as of 2026-07-05" (the archive is not updated).
- **Everything else** uses the non-probability outcomes in `docs/specs/matchups.md`.

## 10. Caveats

- **Federation test period.** It is the same calendar period in which syncs keep adding data. The
  snapshot froze it on 2026-11-14.
- **Grid widening.** Grids were widened twice after optima hit an edge, on validation only. BWF
  was selected on the second grid. The selection files record each choice.
- **The side-1 effect** in federation data is unexplained. It may be seeding or draw position (a
  legitimate pre-match signal) or a listing convention. Settle it before using it.
- **Minors.** Juniors' ratings are research only. Publishing any rating of minors needs the
  owner's decision (ADR-0009/0010).
