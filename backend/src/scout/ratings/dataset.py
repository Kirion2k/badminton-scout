"""The rating-ready dataset (ADR-0012): which singles matches may be rated, and why not the rest.

Reads match data in one REPEATABLE READ transaction (a consistent view while syncs keep writing)
and never changes it. A snapshot freezes the eligible matches with the canonical player ids of
the moment, so a run can be replayed exactly and compared with a later snapshot.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import Connection, Engine, insert, select, text
from sqlalchemy.orm import Session

from scout.analytics.ordering import round_rank
from scout.models import RatingSnapshot, RatingSnapshotMatch
from scout.sources import Use, require_permitted

QUERY_VERSION = 1
BWF_SOURCE = "bwf_historical_compilation"
FAMILIES = ("bwf", "fed")

# A pool category from the event name. Juniors and para athletes are rated in their own pools or
# not at all: they are not competitively comparable with the open draw.
_PARA = re.compile(
    r"\b(para|wh\s?[12]|sl\s?[34]|su\s?5|sh\s?6|ss\s?6|wheelchair|rolstoel|rollstuhl)\b", re.I
)
_JUNIOR = re.compile(
    r"\b(u\s?\d{1,2}|o?\d{1,2}\s?u|under\s?\d{1,2}|boys?|girls?|juniors?|jeugd|jugend|youth|"
    r"minimes?|benjamins?|cadets?|poussins?|pupilles?|mini)\b",
    re.I,
)


def category(event_name: str) -> str:
    """ "para", "junior" or "adult". Masters ("O35", "35+") are adult."""
    if _PARA.search(event_name):
        return "para"
    return "junior" if _JUNIOR.search(event_name) else "adult"


@dataclass(frozen=True, slots=True)
class Candidate:
    match_id: int
    revision_id: int
    day: date
    round: str | None
    status: str
    winner_side: int | None
    discipline: str | None
    event_name: str
    tournament_id: int
    side1: tuple[int, ...]  # canonical player ids
    side2: tuple[int, ...]
    withheld: bool


@dataclass(frozen=True, slots=True)
class Row:
    """One eligible match, frozen into a snapshot."""

    match_id: int
    revision_id: int
    pool: str
    day: date
    rank: int | None
    cluster: int
    a: int
    b: int
    a_won: bool


def classify(family: str, c: Candidate, *, include_retired: bool = False) -> tuple[str | None, str]:
    """(pool, "eligible") or (None, the reason it is not rated). `include_retired` is the
    ADR-0012 sensitivity variant: a retirement with a winner counts as a result."""
    if c.discipline is None:
        return None, "unclassified_event"
    if c.discipline not in ("MS", "WS"):
        return None, "doubles"
    pool = f"{family}:{c.discipline}"
    if family == "fed":
        kind = category(c.event_name)
        if kind == "para":
            return None, "para_event"
        if kind == "junior":
            pool += ":junior"
    if c.status != "completed" and not (include_retired and c.status == "retired"):
        return None, f"status_{c.status}"
    if c.winner_side not in (1, 2):
        return None, "no_winner"
    if len(c.side1) != 1 or len(c.side2) != 1:
        return None, "not_one_player_per_side"
    if c.withheld:
        return None, "withheld_player"
    if c.side1[0] == c.side2[0]:
        return None, "same_player_both_sides"
    return pool, "eligible"


def _sources(conn: Connection, family: str) -> list[str]:
    if family == "bwf":
        return [BWF_SOURCE]
    rows = conn.execute(text("select id from source where id like 'tournamentsoftware%'"))
    return [r[0] for r in rows]


def candidates(conn: Connection, family: str) -> Iterable[Candidate]:
    """Every match of the family's sources with a singles or unknown discipline."""
    sources = _sources(conn, family)
    for s in sources:
        require_permitted(s, Use.LOCAL_RESEARCH)
    canonical = dict(
        conn.execute(
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
    withheld = {
        r[0] for r in conn.execute(text("select id from player where withheld_at is not null"))
    }
    rows = conn.execute(
        text(
            """select m.id, m.normalized_from_revision_id, m.played_on, m.round, m.status,
                      m.winner_side, e.discipline, e.name, t.id,
                      array_agg(msp.source_player_id order by msp.position)
                        filter (where ms.side = 1),
                      array_agg(msp.source_player_id order by msp.position)
                        filter (where ms.side = 2)
               from match m
               join event e on e.id = m.event_id
               join tournament t on t.id = e.tournament_id
               left join match_side ms on ms.match_id = m.id
               left join match_side_player msp on msp.match_side_id = ms.id
               where t.source_id = any(:sources)
                 and (e.discipline is null or e.discipline in ('MS', 'WS', 'MD', 'WD', 'XD'))
               group by m.id, e.id, t.id"""
        ),
        {"sources": sources},
    )
    for mid, rev, day, rnd, status, winner, disc, ename, tid, s1, s2 in rows:
        ids1: list[int] = s1 or []
        ids2: list[int] = s2 or []
        side1 = tuple(canonical[p] for p in ids1)
        side2 = tuple(canonical[p] for p in ids2)
        yield Candidate(
            mid, rev, day, rnd, status, winner, disc, ename, tid, side1, side2,
            withheld=any(p in withheld for p in side1 + side2),
        )  # fmt: skip


def build(
    conn: Connection, family: str, *, include_retired: bool = False
) -> tuple[list[Row], Counter[str]]:
    """The eligible rows in replay order, and counts: `pool` and `excluded:<reason>` keys."""
    rows: list[Row] = []
    counts: Counter[str] = Counter()
    for c in candidates(conn, family):
        pool, reason = classify(family, c, include_retired=include_retired)
        if pool is None:
            counts[f"excluded:{reason}"] += 1
            continue
        counts[pool] += 1
        a_won = c.winner_side == 1
        rows.append(
            Row(c.match_id, c.revision_id, pool, c.day, round_rank(c.round), c.tournament_id,
                c.side1[0], c.side2[0], a_won)
        )  # fmt: skip
    rows.sort(key=lambda r: (r.day, r.rank is None, r.rank or 0, r.cluster, r.match_id))
    return rows, counts


def content_hash(rows: Iterable[Row]) -> str:
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r.match_id):
        h.update(
            f"{r.match_id}|{r.revision_id}|{r.pool}|{r.day}|{r.rank}|{r.cluster}|{r.a}|{r.b}|"
            f"{int(r.a_won)}\n".encode()
        )
    return h.hexdigest()


def snapshot(engine: Engine, family: str, *, include_retired: bool = False) -> int:
    """Freeze the family's eligible matches. Returns the snapshot id."""
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        rows, counts = build(conn, family, include_retired=include_retired)
        if include_retired:
            counts["option:include_retired"] = 1
        conn.rollback()  # read-only
    with Session(engine) as s, s.begin():
        snap = RatingSnapshot(
            family=family, query_version=QUERY_VERSION, content_hash=content_hash(rows),
            counts=dict(counts),
        )  # fmt: skip
        s.add(snap)
        s.flush()
        if rows:
            s.execute(
                insert(RatingSnapshotMatch),
                [{"snapshot_id": snap.id, **asdict(r)} for r in rows],
            )
        return snap.id


def load(session: Session, snapshot_id: int, pool: str) -> list[Row]:
    """A snapshot's pool in replay order."""
    m = RatingSnapshotMatch
    found = session.execute(
        select(m.match_id, m.revision_id, m.pool, m.day, m.rank, m.cluster, m.a, m.b, m.a_won)
        .where(m.snapshot_id == snapshot_id, m.pool == pool)
        .order_by(m.day, m.rank.is_(None), m.rank, m.cluster, m.match_id)
    )
    return [Row(*r) for r in found]
