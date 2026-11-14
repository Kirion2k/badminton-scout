# M8: Can Mynton estimate strength and predict matchups?

2026-11-14. Protocol: ADR-0012, pre-registered in `e48537f` before any model touched real data.

The test splits were read **twice**. An independent review then found a same-day leakage bug and an
unfair batching comparison (see "Review and the second test read" at the end). After the fixes
(`13d67f0`), every configuration was re-selected on validation only. The selections were
committed in `7a756bc` before the test splits were read again. The numbers below are from that
second read. Raw results are in `docs/research/m8-*-results.json` and
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
| Federation MS/WS (adult, junior) | yes, modestly (tuned only) | no (ECE 0.026–0.037; low forecasts 4–8 points too low) | 38% | **no-go:** show ratings-free comparisons only |
| BWF doubles | yes, clearly (TrueSkill) | yes (ECE 0.016) | 92% | **research only** (as instructed) |
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

Every model is scored on the same 4,313 matches (95%). The other 216 have a player with no
earlier day (206) or no connection (10).

| Model | Log loss (95% CI) | Brier | Accuracy | ECE |
|---|---|---|---|---|
| Constant 0.5 | 0.693 | 0.250 | 50.0% | – |
| Win rate (Beta-smoothed, log5) | 0.611 (0.600–0.621) | 0.211 | 66.7% | 0.045 |
| Elo, default (K 32) | 0.561 (0.544–0.577) | 0.192 | 70.4% | 0.024 |
| Elo, tuned (K 40; K 120 for a player's first 20 matches) | 0.550 (0.532–0.566) | 0.187 | 71.0% | 0.019 |
| Glicko-2 (3-day periods, τ insensitive, RD₀ 250) | **0.548** (0.531–0.563) | **0.186** | **71.0%** | 0.022 |

Paired log-loss differences, with 95% cluster-bootstrap intervals over the same matches. Below
zero favours the first model:

| Comparison | Difference | Significant? |
|---|---|---|
| Glicko-2 − win rate | −0.063 (−0.071 to −0.054) | yes |
| Glicko-2 − default Elo | −0.014 (−0.020 to −0.008) | yes |
| Tuned Elo − default Elo | −0.012 (−0.018 to −0.006) | yes: tuning helped |
| **Glicko-2 − tuned Elo** | **−0.002 (−0.005 to +0.001)** | **no: a tie** |

- **Established vs provisional** (Glicko-2):
  - established (both players ≥10 prior matches, 3,620 matches): 0.546, ECE 0.022;
  - provisional (693 matches): 0.558, ECE 0.044.
- **By discipline:** WS is easier (0.498) than MS (0.591).
- **Over time:** 2025 0.543, 2026 0.559; validation years 0.540–0.546. Stable.
- **Calibration (Glicko-2):** close at the extremes. The 0.5–0.7 forecasts are too confident:
  - 0.6–0.7 bin: forecast 0.649, observed 0.584 (n = 551);
  - 0.5–0.6 bin: forecast 0.548, observed 0.504.
- **Sensitivities** (first read, before the fixes; BWF has no unlabelled rounds, so the leakage
  bug did not reach these):
  - counting retirements as results: Glicko-2 0.552;
  - without the 5 identity-flagged players: unchanged (they have no test-period matches).
- **Determinism:** replays are deterministic (identical output hashes).
- **Not adopted, because validation rejected it:** inactivity decay (worse at every setting).
  Round-level vs day-level batching made no material difference.

## 4. Results: federations (test 2026-01-01 → 2026-11-08; 94,605 matches)

Every model is scored on the same **35,912 matches (38%)**:
- **52,113** have a player with no match on an earlier day: federation newcomers often play
  several group matches on their first day, and none of those can be predicted;
- **6,580** are between unconnected players.

| Model | Log loss (95% CI) | Accuracy | ECE |
|---|---|---|---|
| Constant | 0.693 | 50% | – |
| Win rate | 0.610 (0.600–0.619) | 66.2% | 0.030 |
| Elo, default | 0.625 (0.618–0.631): **worse than win rate** (+0.015, +0.011 to +0.020) | 66.7% | 0.082 |
| Elo, tuned (K 96; K 192 for first 10) | 0.592 (0.578–0.604) | 68.1% | 0.037 |
| Glicko-2 (1-day periods) | **0.588** (0.576–0.599) | 67.8% | **0.026** |

- **Tuned models beat the win rate, modestly:**
  - Glicko-2 −0.021 (−0.026 to −0.017);
  - tuned Elo −0.018 (−0.023 to −0.013).
- **Glicko-2 vs tuned Elo:** a tie (−0.003, −0.008 to +0.002).
- **Established players are fine:** Glicko-2 0.532 (n = 9,499).
- **Most predictions are provisional:** 0.608 (n = 26,413), barely better than the win rate
  (0.619).
- **Calibration (Glicko-2):** low forecasts are too low:
  - 0.0–0.1 bin: forecast 0.067, observed 0.105;
  - 0.2–0.3 bin: forecast 0.252, observed 0.303.
  The direction matches the side-1 effect (§10).
- **By pool** (Glicko-2):

  | Pool | Log loss |
  |---|---|
  | Adult MS | 0.613 |
  | Adult WS | 0.595 |
  | Junior MS | 0.570 |
  | Junior WS | 0.564 |

## 5. Doubles (BWF, research only; test 5,895 matches)

| Model | Log loss (95% CI) | Accuracy | ECE | New partnerships (385) |
|---|---|---|---|---|
| Constant | 0.693 | 50% | – | 0.693 |
| Pair Elo (K 64) | 0.568 (0.551–0.584) | 70.6% | 0.019 | 0.675 |
| Player-level team Elo (K 64) | 0.520 (0.505–0.535) | 74.2% | 0.013 | 0.536 |
| **TrueSkill, two teams** (β 25/3, τ 0.5) | **0.512** (0.497–0.526) | **74.6%** | 0.016 | **0.521** |

- **TrueSkill beats team Elo:** −0.008 (−0.011 to −0.005).
- **Player-level models beat pair Elo:** −0.048 to −0.056.
- **Partner changes:** pair-level models know nothing about a new partnership. Player-level models
  carry each player over, which is the decisive advantage.
- **By discipline:** WD is easiest (0.465), then XD (0.514), then MD (0.553).
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
- **Full rebuild only.** A full BWF replay takes under a second, the federations a few seconds.
- `affected_from` reports the earliest day a correction, insertion, removal or identity change
  touches. Tests show predictions before that day are identical after a rebuild.
- **No incremental rebuild.** The first version replayed everything and so saved nothing; the
  review caught this and it was removed. A real one needs stored replay checkpoints, which are
  not worth it at this size.

## 8. Answers

1. **Players with enough history:**
   - BWF: 1,301 with ≥10 singles matches; 377 of them active since 2025.
   - Federations: 3,393 adults and 2,545 juniors with ≥10.
2. **Eligible completed matches:** 48,607 BWF singles; 139,203 federation singles; 54,773 BWF
   doubles.
3. **Best model:**
   - BWF singles: Glicko-2 and tuned Elo tie.
   - Federations: Glicko-2 and tuned Elo tie.
   - Doubles: TrueSkill.
   - The defaults are not good enough: default Elo loses to the win rate on federations.
4. **Calibration:**
   - BWF: good overall (ECE 0.02), mid-range forecasts about 5 points too confident.
   - Federations: low forecasts 4–8 points too low (ECE 0.026–0.037).
5. **Newer players:**
   - BWF provisional: 0.559 vs 0.546 established.
   - Federation provisional: 0.608, barely better than the win rate (0.619).
   - Not reliable enough to show a probability.
6. **National pools:** not comparable with each other: zero connecting matches.
7. **BWF and domestic ratings:** cannot be combined. There are no verified identity links; 0
   shared players.
8. **Matchups without enough evidence:**
   - any cross-federation or BWF-vs-federation pair;
   - federation pairs in different islands (92% of player pairs);
   - any match on a player's first day (55% of federation test matches).
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
    - (e) **Newcomers' first days.** Predict them from a prior (e.g. the event's grade) instead
      of abstaining.
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

## Review and the second test read

An independent review of the M8 diff found ten issues; all were confirmed and fixed (`13d67f0`).

**Four changed what the models see:**
1. **Same-day leakage.** An unlabelled match was predicted after that day's labelled results were
   applied. It is now predicted from the start of the day.
   - BWF has no unlabelled rounds, so BWF results were not affected.
   - 6,522 federation singles were.
2. **Unfair batching comparison.** Abstentions depended on round vs day batching, so tuning
   compared the two on different matches. That is also why the first federation Glicko-2 run
   covered fewer matches. Abstentions are now decided from the start of the day for every model.
3. **Glicko-2 inactivity cap.** Idle deviation was capped at 350, not at the starting deviation.
4. **TrueSkill variance.** It was overwritten, not compounded, within a batch.

**The others:**
- Rating history mixed pools.
- The "incremental" rebuild did no incremental work.
- Event visibility did not follow reclassification, and the privacy allowlist reads German "MD"
  as adult.
- `scout privacy reclassify` could re-apply English codes.
- Four commands did not refresh coverage.
- The reclassification could exceed Postgres's bind-parameter limit.

**What was done:**
- All selections were redone on validation and committed (`7a756bc`) before the test splits were
  read a second time. Federation Elo's optimum hit the K grid's edge (80), so 96 and 128 were added.
- **The second read changed no conclusion:**
  - BWF numbers moved by at most 0.001.
  - Federation coverage fell from 55% to 38%: the first figure counted newcomers' later same-day
    matches.
  - Federation Glicko-2 vs tuned Elo moved from a small significant win to a tie.
- **The cost:** the test periods are no longer untouched. These are the definitive M8 results;
  any later model change should be judged on a new period (data after 2026-11-14).
