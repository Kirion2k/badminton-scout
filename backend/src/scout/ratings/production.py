"""The served BWF singles ratings (ADR-0013): a full replay of a fresh snapshot with the frozen
M8 configuration, stored per player with their component and identity flag. Only BWF singles
are written; no federation or junior pool is ever stored here."""

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from scout.analytics.graph import UnionFind
from scout.analytics.models import Glicko2, Glicko2Config
from scout.analytics.replay import Prediction, replay
from scout.models import RatingCurrent, RatingSnapshot
from scout.ratings import backtest as bt
from scout.ratings.audit import identity
from scout.ratings.dataset import load, snapshot
from scout.ratings.store import save_run

POOLS = ("bwf:MS", "bwf:WS")


def rebuild(engine: Engine, selection: Path, calibration: Path) -> int:
    """Returns the new run id. A full rebuild every time (seconds at this size)."""
    sel = json.loads(selection.read_text())["glicko2"]
    cal = json.loads(calibration.read_text())
    chosen = cal["final"][cal["selected"]]
    config, by_round = sel["config"], sel["by_round"]
    sid = snapshot(engine, "bwf")
    with engine.connect() as c:
        flagged = identity(c).flagged
    with Session(engine) as s:
        snap = s.get(RatingSnapshot, sid)
        if snap is None:
            raise RuntimeError(f"snapshot {sid} vanished")
        rows_by_pool = {pool: load(s, sid, pool) for pool in POOLS}
    as_of = max(r.day for rows in rows_by_pool.values() for r in rows)
    current: list[dict[str, Any]] = []
    preds: list[Prediction] = []
    for pool, rows in rows_by_pool.items():
        model = Glicko2(Glicko2Config(**config))
        preds += replay(model, bt.scored(rows), by_round=by_round)
        model.at(as_of + timedelta(days=model.config.period_days))  # close the last period
        graph = UnionFind()
        played: Counter[int] = Counter()
        last: dict[int, date] = {}
        for r in rows:
            graph.union(r.a, r.b)
            for p in (r.a, r.b):
                played[p] += 1
                last[p] = max(last.get(p, r.day), r.day)
        roots: dict[int, int] = {}
        for p in sorted(played):
            g = model.player(p)
            current.append({
                "pool": pool, "player_id": p, "rating": g.rating, "rd": g.rd, "vol": g.vol,
                "played": played[p], "last_played": last[p],
                "component": roots.setdefault(graph.find(p), len(roots)),
                "identity_flagged": p in flagged,
            })  # fmt: skip
    with Session(engine) as s, s.begin():
        run_id = save_run(
            s, name="glicko2", config={**config, "by_round": by_round}, snapshot_id=sid,
            pool="bwf", kind="full", splits=bt.SPLITS["bwf"], preds=preds,
            metrics={"data_as_of": str(as_of), "snapshot_hash": snap.content_hash,
                     "calibration": chosen["parameters"],
                     "calibration_hash": chosen["calibration_hash"],
                     "calibration_selected": cal["selected"],
                     "identity_flagged": len(flagged)},
        )  # fmt: skip
        s.execute(insert(RatingCurrent), [{"run_id": run_id, **c} for c in current])
    return run_id


def latest_run(session: Session) -> int | None:
    """The newest full BWF run with stored current ratings: the only one the route reads."""
    from scout.models import RatingRun

    return session.scalar(
        select(RatingRun.id)
        .where(
            RatingRun.kind == "full", RatingRun.pool == "bwf", RatingRun.finished_at.is_not(None)
        )
        .order_by(RatingRun.id.desc())
        .limit(1)
    )
