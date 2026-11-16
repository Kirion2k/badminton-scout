"""Prospective evaluation (ADR-0013, ADR-0014): forecasts recorded against a fixture before its
cutoff, scored later against its verified result. This is the only evidence that can release
public probabilities."""

import random
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Literal, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import matchups
from scout.analytics import metrics
from scout.analytics.models import WinRate
from scout.analytics.replay import replay
from scout.fixtures import store
from scout.fixtures.providers import CURATED_SOURCE
from scout.models import (
    Fixture,
    ForecastEvent,
    IngestRun,
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
MAX_FIXTURE_AGE = timedelta(hours=24)  # older fixture data may miss a change of time or players
EVIDENCE_SOURCES = frozenset({CURATED_SOURCE})  # where forecasts may be issued from (ADR-0014)
BWF_RESULT_SOURCES = (BWF_SOURCE, "bwf")


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


def _ratings_current(session: Session, s: matchups.Served) -> None:
    """Refuse when BWF results were imported after the served ratings were built: the ratings
    would not reflect what is already known."""
    newer = session.scalar(
        select(func.count()).select_from(IngestRun).where(
            IngestRun.source_id.in_(BWF_RESULT_SOURCES), IngestRun.status == "succeeded",
            IngestRun.finished_at > s.computed_at,
        )
    )  # fmt: skip
    if newer:
        raise NotEligible("stale rating snapshot: BWF results were imported after the served "
                          "run; run `scout ratings serve-bwf`")  # fmt: skip


def issue_for_fixture(session: Session, fixture_id: int) -> IssuedPrediction:
    """Record a forecast for a fixture before its cutoff (ADR-0014). Refuses anything the route
    would refuse a probability for (except the public flag), and anything not provably before
    the match."""
    f = session.get(Fixture, fixture_id, with_for_update=True)
    if f is None:
        raise NotEligible(f"no fixture {fixture_id}")
    now = session.execute(select(func.clock_timestamp())).scalar_one()  # the database's clock
    if f.source_id not in EVIDENCE_SOURCES:
        raise NotEligible(f"{f.source_id} is not a fixture source forecasts are issued from")
    if f.status != "scheduled":
        raise NotEligible(f"the fixture is {f.status}, not scheduled")
    if f.duplicate_of is not None or session.scalar(
        select(Fixture.id).where(Fixture.duplicate_of == f.id).limit(1)
    ):
        raise NotEligible("the fixture is listed twice: resolve the duplicate first")
    if now - f.retrieved_at > MAX_FIXTURE_AGE:
        raise NotEligible("stale fixture data: last checked over 24 hours ago")
    cut = store.fixture_cutoff(f)
    if now >= cut:
        raise NotEligible(f"past the cutoff ({cut.isoformat()}): the match may have started")
    already = session.scalar(select(IssuedPrediction.id).where(IssuedPrediction.fixture_id == f.id))
    if already is not None:
        raise NotEligible(f"forecast {already} already covers this fixture")
    s = _served(session)
    if f.scheduled_date <= s.data_as_of:
        raise NotEligible(f"the match must be after the ratings' data ({s.data_as_of})")
    _ratings_current(session, s)
    disc = cast(Literal["MS", "WS"], f.discipline)
    a = store.resolved(session, f.side_a_player_id, s.run_id, disc)
    b = store.resolved(session, f.side_b_player_id, s.run_id, disc)
    if a is None or b is None:
        raise NotEligible("unresolved player: not linked to a rated BWF player")
    if a == b:
        raise NotEligible("both sides resolve to the same player")
    pair = (min(a, b), max(a, b))
    same_match = session.scalar(
        select(IssuedPrediction.id).where(
            IssuedPrediction.discipline == disc,
            IssuedPrediction.scheduled_on == f.scheduled_date,
            func.least(IssuedPrediction.player_a, IssuedPrediction.player_b) == pair[0],
            func.greatest(IssuedPrediction.player_a, IssuedPrediction.player_b) == pair[1],
        )
    )
    if same_match is not None:
        raise NotEligible(f"forecast {same_match} already covers this match")
    pool = f"bwf:{disc}"
    ra, rb = _rated(session, s.run_id, pool, a), _rated(session, s.run_id, pool, b)
    if why := matchups.blocker(ra, rb, disc):
        raise NotEligible(why[1])
    snap = session.get(RatingSnapshot, s.snapshot_id)
    run = session.get(RatingRun, s.run_id)
    if snap is None or run is None:
        raise NotEligible("the served run or its snapshot is missing")
    row = IssuedPrediction(
        issued_at=now, scheduled_on=f.scheduled_date, match_ref=f"{f.source_id}:{f.source_key}",
        discipline=disc, player_a=a, player_b=b,
        p_a=matchups.probability(ra, rb, s, f.scheduled_date), config_hash=s.version,
        calibration_hash=run.metrics["calibration_hash"], run_id=s.run_id,
        snapshot_id=s.snapshot_id, snapshot_hash=snap.content_hash, fixture_id=f.id,
        fixture_revision_id=f.revision_id, cutoff_at=cut,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return row


@dataclass(frozen=True)
class Outcome:
    kind: Literal["scored", "void", "conflict", "pending"]
    reason: str
    a_won: bool | None = None


def outcome(session: Session, p: IssuedPrediction) -> Outcome:
    """A forecast's outcome from its fixture's current, verified state (ADR-0014)."""
    f = session.get_one(Fixture, p.fixture_id)
    if session.scalar(select(ForecastEvent.id).where(
        ForecastEvent.fixture_id == f.id, ForecastEvent.kind == "conflict").limit(1)
    ):  # fmt: skip
        return Outcome("conflict", "the verified result changed")
    if not store.is_verified(f):
        return Outcome("pending", f"{f.status}, result not verified"
                       if f.status in store.TERMINAL else f.status)  # fmt: skip
    sides = (store.player_of(session, f.side_a_player_id),
             store.player_of(session, f.side_b_player_id))  # fmt: skip
    forecast = (store.canonical(session, p.player_a), store.canonical(session, p.player_b))
    if set(sides) != set(forecast):
        return Outcome("void", "players changed after the forecast")
    if store.fixture_cutoff(f) <= p.issued_at:
        return Outcome("void", "issued after the corrected start")
    if f.status != "completed":
        return Outcome("void", f.status)
    if f.winner_side is None:  # never: the import requires a winner for a completed fixture
        return Outcome("pending", "completed without a winner")
    return Outcome("scored", "completed", sides[f.winner_side - 1] == forecast[0])


def reconcile(session: Session) -> int:
    """Append a void event for each forecast newly found void (the audit trail; scoring itself
    recomputes outcomes). Returns the number of events added."""
    added = 0
    for p in session.scalars(select(IssuedPrediction).order_by(IssuedPrediction.id)):
        o = outcome(session, p)
        if o.kind != "void":
            continue
        f = session.get_one(Fixture, p.fixture_id)
        seen = session.scalar(select(ForecastEvent.id).where(
            ForecastEvent.prediction_id == p.id, ForecastEvent.kind == "void",
            ForecastEvent.fixture_revision_id == f.revision_id, ForecastEvent.reason == o.reason,
        ).limit(1))  # fmt: skip
        if seen is None:
            session.add(
                ForecastEvent(
                    kind="void",
                    reason=o.reason,
                    fixture_id=f.id,
                    fixture_revision_id=f.revision_id,
                    prediction_id=p.id,
                )
            )
            added += 1
    session.flush()
    return added


def score(session: Session, *, boot: int = 1000) -> dict[str, Any]:
    """Forecasts from evidence sources against ADR-0013's release conditions, with the win-rate
    baseline (from the same snapshot, so it knows nothing the forecast did not) on the same
    matches. Outcomes are recomputed from the fixtures: the same database gives the same report."""
    counts: Counter[str] = Counter()
    voids: Counter[str] = Counter()
    done: list[tuple[IssuedPrediction, bool]] = []
    for p in session.scalars(
        select(IssuedPrediction).join(Fixture, Fixture.id == IssuedPrediction.fixture_id)
        .where(Fixture.source_id.in_(EVIDENCE_SOURCES)).order_by(IssuedPrediction.id)
    ):  # fmt: skip
        o = outcome(session, p)
        counts[o.kind] += 1
        if o.kind == "void":
            voids[o.reason] += 1
        if o.kind == "scored":
            done.append((p, bool(o.a_won)))
    out: dict[str, Any] = {
        "issued": sum(counts.values()), "resolved": len(done), "void": dict(voids),
        "pending": counts["pending"], "conflict": counts["conflict"], "conditions": {},
    }  # fmt: skip
    if not done:
        out["status"] = "no resolved forecasts: release conditions cannot be assessed"
        return out
    ps, ys = [f.p_a for f, _ in done], [int(won) for _, won in done]
    clusters = [f.fixture_id for f, _ in done]
    ll = metrics.cluster_bootstrap(metrics.log_losses(ps, ys), clusters, n=boot)
    baseline: dict[int, WinRate] = {}
    diffs: list[float] = []
    for f, won in done:
        if f.snapshot_id not in baseline:
            wr = WinRate(prior=2.0)
            rows = load(session, f.snapshot_id, "bwf:MS") + load(session, f.snapshot_id, "bwf:WS")
            replay(wr, bt.scored(rows))
            baseline[f.snapshot_id] = wr
        q = baseline[f.snapshot_id].predict(f.player_a, f.player_b)
        y = int(won)
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
