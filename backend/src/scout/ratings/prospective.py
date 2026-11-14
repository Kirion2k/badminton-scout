"""Prospective evaluation (ADR-0013): forecasts recorded before their match, scored later
against verified results. This is the only evidence that can release public probabilities."""

import random
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from scout import matchups
from scout.analytics import metrics
from scout.analytics.models import WinRate
from scout.analytics.replay import replay
from scout.models import (
    IssuedPrediction,
    Player,
    RatingCurrent,
    RatingRun,
    RatingSnapshot,
)
from scout.ratings import backtest as bt
from scout.ratings import production
from scout.ratings.dataset import BWF_SOURCE, load

RELEASE_MIN_RESOLVED = 1_000  # ADR-0013, condition 1
RELEASE_MAX_ECE_UPPER = 0.04  # condition 3
RELEASE_MIN_BIN = 200  # condition 4: bins judged only from this many forecasts
MATCH_WINDOW = timedelta(days=3)


class NotEligible(Exception):
    pass


def _served(session: Session) -> matchups.Served:
    s = production.served(session)
    if s is None:
        raise NotEligible("no served BWF ratings: run `scout ratings serve-bwf` first")
    return s


def _rated(session: Session, run_id: int, pool: str, player: int) -> matchups.Rated:
    p = session.get(Player, player)
    if p is None or p.merged_into_id is not None or p.withheld_at is not None:
        raise NotEligible(f"player {player} is not a current, published player")
    r = session.get(RatingCurrent, (run_id, pool, player))
    if r is None:
        raise NotEligible(f"player {player} has no {pool} rating")
    return matchups.Rated(
        r.rating, r.rd, r.played, r.last_played, r.component, r.identity_flagged, r.vol or 0.06
    )


def issue(
    session: Session, a: int, b: int, discipline: Literal["MS", "WS"], on: date, ref: str
) -> IssuedPrediction:
    """Record a forecast for a match scheduled after the ratings' last match day. Refuses
    anything the route would refuse a probability for (except the public flag)."""
    s = _served(session)
    today = datetime.now(UTC).date()
    if on <= max(s.data_as_of, today):
        # a forecast is evidence only if made before the match: never for today or the past
        raise NotEligible(f"the match must be after today and after the ratings' data "
                          f"({s.data_as_of})")  # fmt: skip
    if a == b:
        raise NotEligible("a player cannot be compared with themselves")
    pair = (min(a, b), max(a, b))
    already = session.scalar(
        select(IssuedPrediction.id).where(
            IssuedPrediction.discipline == discipline,
            IssuedPrediction.scheduled_on == on,
            func.least(IssuedPrediction.player_a, IssuedPrediction.player_b) == pair[0],
            func.greatest(IssuedPrediction.player_a, IssuedPrediction.player_b) == pair[1],
        )
    )
    if already is not None:
        raise NotEligible(f"forecast {already} already covers this match")
    pool = f"bwf:{discipline}"
    ra, rb = _rated(session, s.run_id, pool, a), _rated(session, s.run_id, pool, b)
    if why := matchups.blocker(ra, rb, discipline):
        raise NotEligible(why[1])
    snap = session.get(RatingSnapshot, s.snapshot_id)
    run = session.get(RatingRun, s.run_id)
    if snap is None or run is None:
        raise NotEligible("the served run or its snapshot is missing")
    row = IssuedPrediction(
        scheduled_on=on, match_ref=ref, discipline=discipline, player_a=a, player_b=b,
        p_a=matchups.probability(ra, rb, s, on), config_hash=s.version,
        calibration_hash=run.metrics["calibration_hash"], run_id=s.run_id,
        snapshot_id=s.snapshot_id, snapshot_hash=snap.content_hash,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return row


def resolve(session: Session, verified_by: str) -> dict[str, int]:
    """Fill each open forecast whose match has been imported from the authorised BWF source:
    the same two players on opposite sides, same discipline, within 3 days, completed. A forecast
    matching zero or several results stays open."""
    counts = {"resolved": 0, "no_result_yet": 0, "ambiguous": 0}
    canonical = dict(
        session.execute(
            text(
                """with recursive up(id, root) as (
                       select id, id from player where merged_into_id is null
                       union all
                       select p.id, up.root from player p join up on p.merged_into_id = up.id)
                   select pl.source_player_id, up.root from player_link pl
                   join up on up.id = pl.player_id"""
            )
        ).all()
    )
    q = text(
        """select m.id, m.winner_side, ms.side, msp.source_player_id
           from match m
           join event e on e.id = m.event_id and e.discipline = :disc
           join tournament t on t.id = e.tournament_id and t.source_id = :source
           join match_side ms on ms.match_id = m.id
           join match_side_player msp on msp.match_side_id = ms.id
           where m.status = 'completed' and m.played_on between :lo and :hi"""
    )
    for f in session.scalars(select(IssuedPrediction).where(IssuedPrediction.a_won.is_(None))):
        # only a match played on or after the day the forecast was made can resolve it
        lo = max(f.scheduled_on - MATCH_WINDOW, f.issued_at.date())
        args = {"disc": f.discipline, "source": BWF_SOURCE, "lo": lo,
                "hi": f.scheduled_on + MATCH_WINDOW}  # fmt: skip
        sides_a: dict[int, tuple[int, int]] = {}
        sides_b: dict[int, int] = {}
        for m, w, side, sp in session.execute(q, args):
            if canonical.get(sp) == f.player_a:
                sides_a[m] = (w, side)
            elif canonical.get(sp) == f.player_b:
                sides_b[m] = side
        found = [(m, w, side) for m, (w, side) in sides_a.items()
                 if m in sides_b and sides_b[m] != side]  # fmt: skip
        if not found:
            counts["no_result_yet"] += 1
            continue
        if len(found) > 1:
            counts["ambiguous"] += 1
            continue
        match_id, winner, side = found[0]
        f.a_won, f.resolved_match_id = winner == side, match_id
        f.resolved_at, f.verified_by = datetime.now(UTC), verified_by
        counts["resolved"] += 1
    session.flush()
    return counts


def score(session: Session, *, boot: int = 1000) -> dict[str, Any]:
    """Resolved forecasts against ADR-0013's release conditions, with the win-rate baseline (from
    the same snapshot, so it knows nothing the forecast did not) on the same matches."""
    done = list(
        session.scalars(select(IssuedPrediction).where(IssuedPrediction.a_won.is_not(None)))
    )
    out: dict[str, Any] = {"resolved": len(done), "conditions": {}}
    if not done:
        out["status"] = "no resolved forecasts: release conditions cannot be assessed"
        return out
    ps, ys = [f.p_a for f in done], [int(bool(f.a_won)) for f in done]
    clusters = [f.resolved_match_id or f.id for f in done]
    ll = metrics.cluster_bootstrap(metrics.log_losses(ps, ys), clusters, n=boot)
    baseline: dict[int, WinRate] = {}
    diffs: list[float] = []
    for f in done:
        if f.snapshot_id not in baseline:
            wr = WinRate(prior=2.0)
            rows = load(session, f.snapshot_id, "bwf:MS") + load(session, f.snapshot_id, "bwf:WS")
            replay(wr, bt.scored(rows))
            baseline[f.snapshot_id] = wr
        q = baseline[f.snapshot_id].predict(f.player_a, f.player_b)
        y = int(bool(f.a_won))
        diffs.append(metrics.log_losses([f.p_a], [y])[0] - metrics.log_losses([q], [y])[0])
    vs = metrics.cluster_bootstrap(diffs, clusters, n=boot)
    # ECE's 95% upper bound: resample the resolved forecasts (seeded)
    pairs = list(zip(ps, ys, strict=True))
    rng = random.Random(0)
    eces: list[float] = []
    for _ in range(boot):
        sample = [rng.choice(pairs) for _ in pairs]
        eces.append(metrics.ece([p for p, _ in sample], [y for _, y in sample]))
    eces.sort()
    bins = metrics.reliability(ps, ys)
    # the same forecasts from the favourite's side: what a matchup's track record shows
    fav = metrics.reliability(
        [max(p, 1 - p) for p in ps], [y if p >= 0.5 else 1 - y for p, y in zip(ps, ys, strict=True)]
    )
    judged = [b for b in bins if b.n >= RELEASE_MIN_BIN]
    off = [
        b for b in judged
        if abs(b.observed - b.mean_p) > 1.96 * (b.mean_p * (1 - b.mean_p) / b.n) ** 0.5
    ]  # fmt: skip
    c = out["conditions"]
    c["1_enough_resolved"] = len(done) >= RELEASE_MIN_RESOLVED
    c["2_beats_win_rate"] = vs.hi < 0
    c["3_ece_upper_bound_ok"] = eces[int(0.975 * boot) - 1] <= RELEASE_MAX_ECE_UPPER
    c["4_judged_bins_within_interval"] = bool(judged) and not off
    out.update({
        "log_loss": asdict(ll), "vs_win_rate": asdict(vs), "ece": metrics.ece(ps, ys),
        "ece_upper_95": eces[int(0.975 * boot) - 1],
        "reliability": [asdict(b) for b in bins], "bins_off": [asdict(b) for b in off],
        "favourite_reliability": [asdict(b) for b in fav],
        "status": "all four data conditions hold: needs independent review and owner approval"
        if all(c.values()) else "not met: PUBLIC_PROBABILITIES stays off",
    })  # fmt: skip
    return out
