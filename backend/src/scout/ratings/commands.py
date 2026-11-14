"""`scout ratings ...`: the M8 steps, reproducible from a checkout (ADR-0012).

snapshot -> tune (validation only) -> commit the selection -> evaluate (reads test once).
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from scout.ratings import backtest as bt
from scout.ratings.audit import connectivity, cross_source_duplicates, identity
from scout.ratings.dataset import Row, load, snapshot
from scout.ratings.store import History, save_run

POOLS = {
    "bwf": ("bwf:MS", "bwf:WS"),
    "fed": ("fed:MS", "fed:WS", "fed:MS:junior", "fed:WS:junior"),
}
# the comparisons the report needs: (model, baseline) on the matches both predicted
PAIRS = [
    ("winrate", "constant"), ("elo_default", "constant"), ("elo_default", "winrate"),
    ("elo_tuned", "winrate"), ("elo_tuned", "elo_default"), ("glicko2", "winrate"),
    ("glicko2", "elo_default"), ("glicko2", "elo_tuned"),
]  # fmt: skip
DEFAULTS: dict[str, dict[str, Any]] = {
    "constant": {"config": {}, "by_round": True},
    # ADR-0012 baseline 3: default K, no provisional K, round batching
    "elo_default": {"config": {"k": 32.0}, "by_round": True},
}
MODEL_OF = {"constant": "constant", "winrate": "winrate", "elo_default": "elo",
            "elo_tuned": "elo", "glicko2": "glicko2"}  # fmt: skip


def rows_of(session: Session, snapshot_id: int, family: str) -> list[Row]:
    return [r for pool in POOLS[family] for r in load(session, snapshot_id, pool)]


def take_snapshot(engine: Engine, family: str, *, include_retired: bool = False) -> int:
    return snapshot(engine, family, include_retired=include_retired)


def tune(engine: Engine, family: str, snapshot_id: int) -> dict[str, Any]:
    """The best configuration per model on validation. Write it to a file and commit it before
    `evaluate`: the commit is the record that the test split was not used to choose."""
    with Session(engine) as s:
        rows = rows_of(s, snapshot_id, family)
    selected: dict[str, Any] = {"snapshot": snapshot_id, "family": family, **DEFAULTS}
    for name, key in (("winrate", "winrate"), ("elo", "elo_tuned"), ("glicko2", "glicko2")):
        best = bt.tune(name, rows, bt.SPLITS[family])[0]
        selected[key] = {"config": best.config, "by_round": best.by_round,
                         "validation_log_loss": best.validation_log_loss}  # fmt: skip
    return selected


def evaluate(engine: Engine, family: str, selection: Path, out: Path) -> dict[str, Any]:
    """Score every selected model on the test split, once, and store the runs."""
    sel = json.loads(selection.read_text())
    splits = bt.SPLITS[family]
    with Session(engine) as s:
        rows = rows_of(s, sel["snapshot"], family)
    pools = {r.match_id: r.pool for r in rows}
    result: dict[str, Any] = {"snapshot": sel["snapshot"], "family": family, "models": {},
                              "paired_test": {}}  # fmt: skip
    preds: dict[str, list[bt.Prediction]] = {}
    for key, name in MODEL_OF.items():
        cfg, by_round = sel[key]["config"], sel[key]["by_round"]
        history = History()
        p = bt.run(name, cfg, rows, by_round=by_round, after_batch=history)
        preds[key] = p
        val = bt.evaluate(p, splits, "validation", pools=pools)
        test = bt.evaluate(p, splits, "test", unseal=True, pools=pools)
        with Session(engine) as s, s.begin():
            run_id = save_run(
                s, name=name, config={**cfg, "by_round": by_round}, snapshot_id=sel["snapshot"],
                pool=family, kind="backtest", splits=splits, preds=p,
                metrics={"validation": val["all"], "test": test["all"]}, history=history,
            )  # fmt: skip
        result["models"][key] = {"name": name, "config": cfg, "by_round": by_round,
                                 "run_id": run_id, "validation": val, "test": test}  # fmt: skip
    for a, b in PAIRS:
        result["paired_test"][f"{a}-{b}"] = bt.paired(preds[a], preds[b], splits, "test",
                                                      unseal=True)  # fmt: skip
    again = bt.run("glicko2", sel["glicko2"]["config"], rows, by_round=sel["glicko2"]["by_round"])
    result["deterministic"] = bt.output_hash(again) == bt.output_hash(preds["glicko2"])
    out.write_text(json.dumps(result, indent=1, default=str))
    return result


def audit(engine: Engine, snapshots: dict[str, int], out: Path) -> dict[str, Any]:
    """Identity flags, cross-source duplicates and connectivity, as counts."""
    with engine.connect() as c:
        ident = identity(c)
        dupes = cross_source_duplicates(c)
    with Session(engine) as s:
        source_of = dict(s.execute(text("select id, source_id from tournament")).all())
        rows = [r for fam, sid in snapshots.items() for r in rows_of(s, sid, fam)]
    families = [{p for r in rows if r.pool.startswith(f) for p in (r.a, r.b)} for f in snapshots]
    shared: set[int] = families[0].intersection(*families[1:]) if len(families) > 1 else set()
    result = {
        "bwf_identity": {"players": ident.players,
                         "two_tournaments_same_day": len(ident.two_tournaments_same_day),
                         "both_genders": len(ident.both_genders),
                         "twice_in_a_knockout_round": len(ident.twice_in_a_round)},
        "cross_source_duplicates": dupes,
        "players_in_more_than_one_family": len(shared),
        "connectivity": connectivity(rows, source_of),
    }  # fmt: skip
    out.write_text(json.dumps(result, indent=1, default=str))
    return result


def calibrate(engine: Engine, run_id: int, out: Path) -> dict[str, Any]:
    """ADR-0013: fold comparison and the final fit on 2012-2024, then a diagnostic-only view of
    the previously examined 2025-2026 period (never used to choose or fit anything)."""
    from dataclasses import asdict

    from scout.ratings import calibrate as cal

    forecasts = cal.load(engine, run_id)
    dev = cal.development(forecasts)
    fold_result = cal.folds(dev)
    chosen = cal.select(fold_result)
    final = {kind: cal.fit(kind, dev) for kind in cal.CANDIDATES}
    examined = [f for f in forecasts if f.day > cal.DEV_END]
    result: dict[str, Any] = {
        "run_id": run_id,
        "development": {"from": str(cal.DEV_START), "to": str(cal.DEV_END), "n": len(dev)},
        "folds": fold_result,
        "selected": chosen,
        "final": {
            kind: {
                "parameters": asdict(c),
                "calibration_hash": cal.calibration_hash(c),
                "development": {g: cal.summary(c, fs) for g, fs in cal.groups(dev).items()},
            }
            for kind, c in final.items()
        },
        "previously_examined_diagnostic_only": {
            "note": "2025-01-01 to 2026-07-05 was read twice in M8 (ADR-0013): not evidence",
            "by_candidate": {
                kind: {g: cal.summary(c, fs) for g, fs in cal.groups(examined).items()}
                for kind, c in final.items()
            },
        },
    }
    out.write_text(json.dumps(result, indent=1, default=str))
    return result
