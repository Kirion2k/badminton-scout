"""Deterministic synthetic data for frontend end-to-end tests. Invented names and ids only.

Runs only against a database whose name ends in `_e2e`, and never with SCOUT_ENV=production.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from scout import identity
from scout.ingest.operations import TsMatchRow, TsTournament
from scout.ingest.tournamentsoftware import ingest_rows, ingest_tournaments
from scout.models import IdentityCandidate, IngestRun, Player, PlayerLink, SourcePlayer, Tournament
from scout.privacy import is_adult_event

SPRING = "aaaaaaaa-0000-0000-0000-000000000001"
AUTUMN = "aaaaaaaa-0000-0000-0000-000000000002"
JUNIORS = "aaaaaaaa-0000-0000-0000-000000000003"

Side = tuple[tuple[str, str, str], ...]  # (tournament player id, name, member id)


def _row(
    tournament: str, draw: int, event: str, round_: str, side1: Side, side2: Side, *,
    winner: int | None, points: tuple[int, ...] = (), message: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    members = [
        f"T{t}P{p}MemberID={m}"
        for t, side in ((1, side1), (2, side2))
        for p, (_, _, m) in enumerate(side, start=1)
    ]
    out: dict[str, Any] = {
        "event": event,
        "drawHref": f"https://ba.tournamentsoftware.com/sport/draw.aspx?id={tournament}&draw={draw}",
        "round": round_,
        "info": "Duration: 34m | Court 2",
        "side1Ids": [p[0] for p in side1],
        "side1Names": [p[1] for p in side1],
        "side2Ids": [p[0] for p in side2],
        "side2Names": [p[1] for p in side2],
        "rowClasses": [f"match__row{' has-won' if winner == s else ''}" for s in (1, 2)],
        "points": [str(p) for p in points],
        "h2h": "https://ba.tournamentsoftware.com/head-2-head?OrganizationCode=e2e&"
        + "&".join(members),
    }
    if message:
        out["message"] = message
    return out


ALEX = ("1", "Alex TESTER", "E2E001")
SAM = ("2", "Sam EXAMPLE", "E2E002")
KIM = ("3", "Kim SAMPLE", "E2E003")
LEE = ("4", "Lee PLACEHOLDER", "E2E004")
PAT = ("5", "Pat DUMMY", "E2E005")
CHRIS = ("6", "Chris MOCK", "E2E006")
JORDAN_A = ("7", "Jordan DUPLICATE", "E2E007")  # will be merged into JORDAN_B
JORDAN_B = ("8", "Jordan DUPLICATE", "E2E008")
KID1 = ("90", "Junior PERSON", "E2E090")
KID2 = ("91", "Junior OTHER", "E2E091")
PARA = ("95", "Para ATHLETE", "E2E095")

DAYS: list[tuple[str, date, list[dict[str, Any]]]] = [
    (SPRING, date(2026, 3, 14), [
        _row(SPRING, 1, "MS A", "Round 1", (ALEX,), (SAM,), winner=1, points=(21, 15, 21, 18)),
        _row(SPRING, 1, "MS A", "Semi final", (ALEX,), (PAT,), winner=2, points=(19, 21, 21, 17, 18, 21)),
        _row(SPRING, 2, "XD Open", "Round 1", (ALEX, KIM), (CHRIS, LEE), winner=1, points=(21, 12, 21, 9)),
        _row(SPRING, 3, "MS A Reserve", "Round 1", (JORDAN_A,), (SAM,), winner=1, points=(21, 19, 21, 19)),
        _row(SPRING, 4, "BS U15", "Round 1", (KID1,), (KID2,), winner=1, points=(21, 5, 21, 7)),
        _row(SPRING, 5, "SL3 Singles", "Round 1", (PARA,), (SAM,), winner=1, points=(21, 18, 21, 16)),
    ]),
    (SPRING, date(2026, 3, 15), [
        _row(SPRING, 1, "MS A", "Final", (SAM,), (CHRIS,), winner=1, points=(21, 11, 21, 13)),
        _row(SPRING, 2, "XD Open", "Semi final", (ALEX, KIM), (PAT, LEE), winner=1, message="Walkover"),
        _row(SPRING, 3, "MS A Reserve", "Final", (JORDAN_B,), (CHRIS,), winner=2, points=(15, 21, 16, 21)),
    ]),
    (AUTUMN, date(2026, 9, 5), [
        _row(AUTUMN, 1, "MS B", "Round 1", (ALEX,), (CHRIS,), winner=1, points=(21, 9, 8, 3), message="Retired"),
        _row(AUTUMN, 1, "MS B", "Round 2", (ALEX,), (SAM,), winner=None, message="Cancelled"),
        _row(AUTUMN, 1, "MS B", "Final", (ALEX,), (PAT,), winner=2, points=(17, 21, 19, 21)),
    ]),
    (JUNIORS, date(2026, 6, 1), [
        _row(JUNIORS, 1, "GS U13", "Round 1", (KID1,), (KID2,), winner=2, points=(15, 21, 12, 21)),
    ]),
]  # fmt: skip

LISTINGS = [
    {"name": "Synthetic Spring Open 2026", "subheading": "Synthetic Association | Testville",
     "dates": ["2026-03-14 00:00", "2026-03-15 23:59"], "id": SPRING},
    {"name": "Synthetic Autumn Classic 2026 incorporating the Open Graded Championships and Masters Series (Silver) $1200 Prizemoney",
     "subheading": "Synthetic Association | Sampleton",
     "dates": ["2026-09-05 00:00"], "id": AUTUMN},
    {"name": "Synthetic Junior Championships 2026", "subheading": "Synthetic Association | Testville",
     "dates": ["2026-06-01 00:00"], "id": JUNIORS},
]  # fmt: skip


def seed(session: Session, out: Path | None = None) -> dict[str, int]:
    name = session.bind.engine.url.database if session.bind else ""  # type: ignore[union-attr]
    if not (name or "").endswith("_e2e"):
        raise RuntimeError(f"refusing to seed database {name!r}: only *_e2e databases")
    session.execute(
        text(
            "TRUNCATE game, match_side_player, match_side, match, event, tournament, player_link, "
            "identity_candidate, identity_decision, player, source_player, ingest_issue, "
            "raw_record_revision, raw_record, ingest_run, request_event, request_ledger CASCADE"
        )
    )
    run = IngestRun(source_id="synthetic", status="succeeded")
    session.add(run)
    session.flush()
    rows = [
        {"name": t["name"], "href": f"https://ba.tournamentsoftware.com/sport/tournament?id={t['id']}",
         "subheading": t["subheading"], "dates": t["dates"]}
        for t in LISTINGS
    ]  # fmt: skip
    ingest_tournaments(session, run, [TsTournament.model_validate(r) for r in rows], rows)
    for _, day, day_rows in DAYS:
        items = [TsMatchRow.model_validate(r) for r in day_rows]
        ingest_rows(session, run, day, items, day_rows)
    # the Jordan pair: same name, different member ids. A reviewed merge, as a human would make it
    identity.generate_candidates(session)
    a, b = (
        session.scalars(
            select(SourcePlayer.id).filter_by(source_key=f"member:e2e/{m.lower()}")
        ).one()
        for m in (JORDAN_A[2], JORDAN_B[2])
    )
    candidate = session.scalars(
        select(IdentityCandidate).filter_by(
            source_player_a_id=min(a, b), source_player_b_id=max(a, b)
        )
    ).one()
    identity.merge(session, candidate.id, "e2e fixture: same person", "seed:e2e")
    session.commit()

    def player(member: str) -> int:
        sp = session.scalars(
            select(SourcePlayer.id).filter_by(source_key=f"member:e2e/{member.lower()}")
        ).one()
        return session.scalars(select(PlayerLink.player_id).filter_by(source_player_id=sp)).one()

    merged_from = session.scalars(select(Player.id).where(Player.merged_into_id.is_not(None))).one()
    ids = {
        "alex": player(ALEX[2]),
        "sam": player(SAM[2]),
        "kim": player(KIM[2]),
        "jordan": player(JORDAN_A[2]),
        "jordanMergedFrom": merged_from,
        "junior": player(KID1[2]),
        "para": player(PARA[2]),
        "spring": session.scalars(select(Tournament.id).filter_by(source_key=SPRING)).one(),
        "autumn": session.scalars(select(Tournament.id).filter_by(source_key=AUTUMN)).one(),
        "juniorTournament": session.scalars(
            select(Tournament.id).filter_by(source_key=JUNIORS)
        ).one(),
    }
    # the classifier must see the fixture's junior and para events as restricted
    if is_adult_event("BS U15", "MS") or is_adult_event("SL3 Singles", None):
        raise RuntimeError("the fixture's junior or para event is classed as adult")
    if out:
        out.write_text(json.dumps(ids, indent=2) + "\n")
    return ids
