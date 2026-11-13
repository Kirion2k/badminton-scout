"""Read API over normalized data. Only redistributable events are ever visible (ADR-0009)."""

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, func, literal, or_, select
from sqlalchemy.orm import Session

import scout.privacy
from scout.db import get_session
from scout.ingest.tournamentsoftware import discipline_of
from scout.models import (
    Event,
    Game,
    IngestIssue,
    IngestRun,
    Match,
    MatchSide,
    MatchSidePlayer,
    Player,
    PlayerLink,
    RawRecord,
    RawRecordRevision,
    Source,
    SyncRun,
    Tournament,
    TournamentDiscovery,
)
from scout.privacy import is_redistributable_event
from scout.sources import SOURCES

router = APIRouter(prefix="/v1", tags=["players"])
DB = Annotated[Session, Depends(get_session)]


class PlayerRef(BaseModel):
    id: int
    name: str
    withheld: bool = False  # removal request: the name is masked and there is no profile


WITHHELD_NAME = "Name withheld"


class PlayerHit(PlayerRef):
    matches: int
    last_played: date | None


class Record(BaseModel):
    played: int
    won: int
    lost: int
    walkovers: int  # included in won/lost, listed so a record can be read honestly


class TournamentAppearance(BaseModel):
    id: int
    name: str | None
    start_date: date | None
    matches: int
    won: int
    lost: int


class OpponentRecord(PlayerRef):
    played: int  # decided matches only
    won: int
    lost: int


class DisciplineRecord(BaseModel):
    discipline: str  # MS, WS, MD, WD, XD
    won: int
    lost: int  # decided matches only, as in Record


class PlayerProfile(PlayerRef):
    record: Record
    by_discipline: list[DisciplineRecord]  # most played first
    tournaments: int
    tournament_history: list[TournamentAppearance]  # newest first
    opponents: list[OpponentRecord]  # most played first, at most 10
    first_played: date | None
    last_played: date | None
    disciplines: list[str]
    sources: list[str]  # attribution of every source the profile draws on
    data_retrieved_at: datetime | None


class TournamentRef(BaseModel):
    id: int
    name: str | None


class PlayerMatch(BaseModel):
    id: int
    played_on: date | None
    tournament: TournamentRef
    event: str
    discipline: str | None
    round: str | None
    status: str
    result: Literal["won", "lost"] | None  # from this player's side; None if not decided
    games: list[tuple[int, int]]  # this player's points first
    partners: list[PlayerRef]
    opponents: list[PlayerRef]
    source: str  # attribution
    retrieved_at: datetime


class MatchPage(BaseModel):
    items: list[PlayerMatch]
    total: int
    limit: int
    offset: int


class EventSummary(BaseModel):
    name: str
    discipline: str | None
    matches: int


ImportStatus = Literal["complete", "complete_with_gaps", "partial", "in_progress"]


class ImportState(BaseModel):
    """How much of a tournament's published results we hold (None: not imported via the queue)."""

    status: ImportStatus
    unimported_matches: int  # real matches the source shows that we could not import
    note: str  # one plain sentence for the page


class TournamentSummary(TournamentRef):
    source_id: str
    import_state: ImportState | None
    start_date: date | None
    end_date: date | None
    location: str | None
    organiser: str | None
    events: int
    matches: int
    source: str


class TournamentPage(BaseModel):
    items: list[TournamentSummary]
    total: int
    limit: int
    offset: int


class TournamentMatch(BaseModel):
    id: int
    played_on: date | None
    event: str
    discipline: str | None
    round: str | None
    status: str
    winner_side: int | None
    games: list[tuple[int, int]]  # side 1 points first
    side1: list[PlayerRef]
    side2: list[PlayerRef]


class TournamentMatchPage(BaseModel):
    items: list[TournamentMatch]
    total: int
    limit: int
    offset: int


ProviderStatus = Literal[
    "connected_importing",
    "connected_read_only",
    "partially_validated",
    "pending_access",
    "access_unavailable",
    "source_error",
]


class ProviderCoverage(BaseModel):
    source_id: str
    name: str
    attribution: str
    status: ProviderStatus  # derived from registered operations and real ingest results
    limitations: list[str]
    discovered_tournaments: int  # listed by the portal; not a claim that results exist
    # Published data only. Stored-but-withheld volumes stay internal (`scout report coverage`):
    # stored minus public would count junior and para records (ADR-0009 §2).
    public_tournaments: int  # with at least one match that may be shown
    public_matches: int
    public_players: int
    first_played: date | None  # public matches only
    last_played: date | None
    last_retrieved_at: datetime | None
    awaiting_import: int  # queued, owned by this provider; listings only, no results implied
    last_sync_at: datetime | None
    last_sync_status: str | None  # succeeded, incomplete (budget used up), failed or skipped


class Coverage(BaseModel):
    providers: list[ProviderCoverage]
    excluded: list[str]  # categories never served, and why
    public_tournaments: int  # across providers
    public_matches: int
    public_players: int  # distinct people, not summed per provider
    last_retrieved_at: datetime | None
    last_sync_at: datetime | None  # latest scheduled pass that finished (succeeded or incomplete)
    next_sync_at: datetime | None  # set by the scheduler; None = never scheduled; past = overdue
    awaiting_import: int  # tournaments queued (including ones whose owner is not yet checked)


class TournamentDetail(TournamentRef):
    organiser: str | None
    location: str | None
    start_date: date | None
    end_date: date | None
    events: list[EventSummary]
    source: str
    source_id: str
    import_state: ImportState | None


# Rejections that lose a real match. Byes and empty draw slots are not matches.
_LOSS_KINDS = (
    "unknown_message", "unlinked_player", "unexpected_sides", "key_collision", "names_mismatch",
    "malformed_score", "discipline_mismatch", "winner_without_play", "no_winner",
    "walkover_with_score", "winner_disagrees_with_score", "implausible_badminton_score",
    "missing_identifiers",
)  # fmt: skip


def _import_states(db: Session, tournaments: list[Tournament]) -> dict[int, ImportState]:
    """Completeness per tournament, from the import queue and the records we could not use."""
    if not tournaments:
        return {}
    by_key = {(t.source_id, t.source_key.lower()): t.id for t in tournaments}
    source_of = {guid: source for source, guid in by_key}
    guids = list(source_of)
    # the queue row of the tournament's own source only (a copy elsewhere is not its owner)
    queue = {
        guid: status
        for guid, owner, status in db.execute(
            select(
                TournamentDiscovery.guid,
                TournamentDiscovery.owner_source,
                TournamentDiscovery.status,
            ).where(TournamentDiscovery.guid.in_(guids))
        )
        if owner == source_of[guid]
    }
    lost: Counter[str] = Counter()
    # stored records without a match: the latest issue decides (a later revision may be a bye)
    tournament_of = func.lower(func.split_part(RawRecord.source_record_key, "|", 1))
    latest: dict[int, tuple[str, str, str]] = {}
    for record_id, guid, kind, event in db.execute(
        select(
            RawRecord.id,
            tournament_of,
            IngestIssue.kind,
            RawRecordRevision.payload["event"].astext,
        )
        .join(IngestIssue, IngestIssue.raw_record_id == RawRecord.id)
        .join(RawRecordRevision, RawRecordRevision.id == RawRecord.current_revision_id)
        .where(
            tournament_of.in_(guids),
            ~select(Match.id).where(Match.raw_record_id == RawRecord.id).exists(),
        )
        .order_by(IngestIssue.id)
    ):
        latest[record_id] = (guid, kind, event or "")
    for guid, kind, event in latest.values():
        # only matches that would be served count: a gap count must not reveal hidden events
        if kind in _LOSS_KINDS and is_redistributable_event(event, discipline_of(event)):
            lost[guid] += 1
    # two different matches on one locator: neither is stored, so count them from the issue
    collided: dict[str, tuple[str, int]] = {}
    collision_key = IngestIssue.detail["key"].astext
    for key, rows in db.execute(
        select(collision_key, IngestIssue.detail["rows"].astext).where(
            IngestIssue.kind == "key_collision",
            func.lower(func.split_part(collision_key, "|", 1)).in_(guids),
            ~select(RawRecord.id).where(RawRecord.source_record_key == collision_key).exists(),
        )
    ):
        size = int(rows) if rows else 2  # issues logged before 2026-11-13 lack the row count
        collided[key] = (key.split("|", 1)[0].lower(), max(size, collided.get(key, ("", 0))[1]))
    for guid, size in collided.values():
        lost[guid] += size
    states: dict[int, ImportState] = {}
    for (_, guid), tid in by_key.items():
        status, missing = queue.get(guid), lost[guid]
        if status is None:
            continue
        gaps = f"{missing} match{'es' if missing != 1 else ''} on the source could not be imported."
        if status == "not_finished":
            state = ImportState(
                status="in_progress",
                unimported_matches=missing,
                note="Still being played: new results are added daily.",
            )
        elif status == "login_required":
            state = ImportState(
                status="partial",
                unimported_matches=missing,
                note="Some match days need a login on the source and are not included.",
            )
        elif status != "complete":  # new, partial, failed, or anything unexpected: never complete
            state = ImportState(
                status="partial",
                unimported_matches=missing,
                note="Import not finished: the remaining match days follow in the next sync.",
            )
        elif missing:
            state = ImportState(status="complete_with_gaps", unimported_matches=missing, note=gaps)
        else:
            state = ImportState(
                status="complete",
                unimported_matches=0,
                note="Every published match day was imported.",
            )
        states[tid] = state
    return states


def _visible_matches() -> Select[int]:
    """Ids of matches that may be served: the single place ADR-0009 is enforced for reads."""
    return select(Match.id).join(Event, Event.id == Match.event_id).where(Event.redistributable)


def _sides_of(player_id: int) -> Select[int, int]:
    """(match_id, side) for every visible match the player took part in."""
    return (
        select(MatchSide.match_id, MatchSide.side)
        .join(MatchSidePlayer, MatchSidePlayer.match_side_id == MatchSide.id)
        .join(PlayerLink, PlayerLink.source_player_id == MatchSidePlayer.source_player_id)
        .where(PlayerLink.player_id == player_id, MatchSide.match_id.in_(_visible_matches()))
    )


def _people_and_games(
    db: Session, match_ids: list[int]
) -> tuple[dict[tuple[int, int], list[PlayerRef]], dict[int, list[tuple[int, int]]]]:
    """Players per (match, side) and games per match, for already-visible match ids."""
    people: dict[tuple[int, int], list[PlayerRef]] = defaultdict(list)
    for match_id, side, pid, name, withheld_at in db.execute(
        select(
            MatchSide.match_id,
            MatchSide.side,
            Player.id,
            Player.display_name,
            Player.withheld_at,
        )
        .join(MatchSidePlayer, MatchSidePlayer.match_side_id == MatchSide.id)
        .join(PlayerLink, PlayerLink.source_player_id == MatchSidePlayer.source_player_id)
        .join(Player, Player.id == PlayerLink.player_id)
        .where(MatchSide.match_id.in_(match_ids))
        .order_by(MatchSide.match_id, MatchSide.side, MatchSidePlayer.position)
    ):
        withheld = withheld_at is not None
        people[(match_id, side)].append(  # no id either: appearances must not be linkable
            PlayerRef(
                id=0 if withheld else pid,
                name=WITHHELD_NAME if withheld else name,
                withheld=withheld,
            )
        )
    games: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for g in db.scalars(select(Game).where(Game.match_id.in_(match_ids)).order_by(Game.number)):
        games[g.match_id].append((g.side1_points, g.side2_points))
    return people, games


def _player_or_redirect(db: Session, player_id: int, suffix: str = "") -> Player | RedirectResponse:
    player = db.get(Player, player_id)
    hops, withheld = 0, player is not None and player.withheld_at is not None
    while player is not None and player.merged_into_id is not None and hops < 5:  # ADR-0003
        player, hops = db.get(Player, player.merged_into_id), hops + 1
        withheld = withheld or (player is not None and player.withheld_at is not None)
    if player is None or player.merged_into_id is not None or withheld:
        raise HTTPException(404, "no such player")  # withheld: the same answer as unknown
    if not db.scalar(select(func.count()).select_from(_sides_of(player.id).subquery())):
        raise HTTPException(404, "no such player")  # also hides players seen only in junior events
    if player.id != player_id:
        return RedirectResponse(f"/v1/players/{player.id}{suffix}", status_code=308)
    return player


@router.get("/players")
def search_players(
    db: DB,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: int = Query(10, ge=1, le=50),
) -> list[PlayerHit]:
    """Players by name, tolerant of typos and partial names."""
    score = func.greatest(
        func.similarity(Player.display_name, q), func.word_similarity(q, Player.display_name)
    )
    visible = (
        select(
            PlayerLink.player_id,
            func.count().label("n"),
            func.max(Match.played_on).label("last"),
        )
        .join(MatchSidePlayer, MatchSidePlayer.source_player_id == PlayerLink.source_player_id)
        .join(MatchSide, MatchSide.id == MatchSidePlayer.match_side_id)
        .join(Match, Match.id == MatchSide.match_id)
        .where(Match.id.in_(_visible_matches()))
        .group_by(PlayerLink.player_id)
        .subquery()
    )
    rows = db.execute(
        select(Player.id, Player.display_name, visible.c.n, visible.c.last)
        .join(visible, visible.c.player_id == Player.id)
        .where(
            Player.merged_into_id.is_(None),
            Player.withheld_at.is_(None),
            # indexable trigram operators (similarity 0.3 / word similarity 0.6 thresholds)
            or_(
                Player.display_name.op("%", is_comparison=True)(q),
                literal(q).op("<%", is_comparison=True)(Player.display_name),
            ),
        )
        .order_by(score.desc(), visible.c.n.desc())
        .limit(limit)
    ).all()
    return [PlayerHit(id=i, name=n, matches=c, last_played=d) for i, n, c, d in rows]


@router.get("/players/{player_id}", response_model=PlayerProfile)
def player_profile(db: DB, player_id: int) -> PlayerProfile | RedirectResponse:
    player = _player_or_redirect(db, player_id)
    if isinstance(player, RedirectResponse):
        return player
    sides = _sides_of(player_id).subquery()
    rows = db.execute(
        select(
            Match.id,
            Match.played_on,
            Match.status,
            Match.winner_side,
            sides.c.side,
            Event.discipline,
            Event.tournament_id,
            Source.attribution,
            IngestRun.started_at,
        )
        .join(sides, sides.c.match_id == Match.id)
        .join(Event, Event.id == Match.event_id)
        .join(RawRecordRevision, RawRecordRevision.id == Match.normalized_from_revision_id)
        .join(IngestRun, IngestRun.id == RawRecordRevision.last_seen_run_id)
        .join(Source, Source.id == IngestRun.source_id)
    ).all()
    decided = [r for r in rows if r.winner_side is not None]
    won = sum(r.winner_side == r.side for r in decided)
    days = [r.played_on for r in rows if r.played_on]

    per_tournament: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        tally = per_tournament[r.tournament_id]
        tally[0] += 1
        if r.winner_side is not None:
            tally[1 if r.winner_side == r.side else 2] += 1
    tournaments = {
        t.id: t for t in db.scalars(select(Tournament).where(Tournament.id.in_(per_tournament)))
    }
    history = sorted(
        (
            TournamentAppearance(
                id=tid,
                name=tournaments[tid].name,
                start_date=tournaments[tid].start_date,
                matches=n,
                won=w,
                lost=lo,
            )
            for tid, (n, w, lo) in per_tournament.items()
        ),
        key=lambda a: (a.start_date or date.min, a.id),
        reverse=True,
    )

    my_side = {r.id: r.side for r in decided}
    outcome = {r.id: r.winner_side == r.side for r in decided}
    faced: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    names: dict[int, str] = {}
    for match_id, side, pid, name in db.execute(
        select(MatchSide.match_id, MatchSide.side, Player.id, Player.display_name)
        .join(MatchSidePlayer, MatchSidePlayer.match_side_id == MatchSide.id)
        .join(PlayerLink, PlayerLink.source_player_id == MatchSidePlayer.source_player_id)
        .join(Player, Player.id == PlayerLink.player_id)
        .where(MatchSide.match_id.in_(list(my_side)), Player.withheld_at.is_(None))
    ):
        if side != my_side[match_id]:
            faced[pid][0 if outcome[match_id] else 1] += 1
            names[pid] = name
    opponents = sorted(
        (
            OpponentRecord(id=pid, name=names[pid], played=w + lo, won=w, lost=lo)
            for pid, (w, lo) in faced.items()
        ),
        key=lambda o: (-o.played, o.name),
    )[:10]
    return PlayerProfile(
        id=player.id,
        name=player.display_name,
        record=Record(
            played=len(decided),
            won=won,
            lost=len(decided) - won,
            walkovers=sum(r.status == "walkover" for r in decided),
        ),
        by_discipline=sorted(
            (
                DisciplineRecord(discipline=d, won=w, lost=n - w)
                for d in {r.discipline for r in decided if r.discipline}
                for n, w in [
                    (
                        sum(r.discipline == d for r in decided),
                        sum(r.discipline == d and r.winner_side == r.side for r in decided),
                    )
                ]
            ),
            key=lambda x: -(x.won + x.lost),
        ),
        tournaments=len(per_tournament),
        tournament_history=history,
        opponents=opponents,
        first_played=min(days, default=None),
        last_played=max(days, default=None),
        disciplines=sorted({r.discipline for r in rows if r.discipline}),
        sources=sorted({r.attribution for r in rows}),
        data_retrieved_at=max((r.started_at for r in rows), default=None),
    )


def _result(winner_side: int | None, side: int) -> Literal["won", "lost"] | None:
    if winner_side is None:
        return None
    return "won" if winner_side == side else "lost"


@router.get("/players/{player_id}/matches", response_model=MatchPage)
def player_matches(
    db: DB,
    player_id: int,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    discipline: Literal["MS", "WS", "MD", "WD", "XD"] | None = None,
    tournament_id: int | None = None,
    year: int | None = Query(None, ge=1900, le=2100),
    result: Literal["won", "lost"] | None = None,
) -> MatchPage | RedirectResponse:
    """Newest first, from this player's point of view. Filters combine with AND."""
    player = _player_or_redirect(db, player_id, "/matches")
    if isinstance(player, RedirectResponse):
        return player
    sides = _sides_of(player_id).subquery()
    filters: list[ColumnElement[bool]] = []
    if discipline:
        filters.append(Event.discipline == discipline)
    if tournament_id is not None:
        filters.append(Event.tournament_id == tournament_id)
    if year is not None:
        filters.append(func.extract("year", Match.played_on) == year)
    if result == "won":
        filters.append(Match.winner_side == sides.c.side)
    elif result == "lost":
        filters.append(Match.winner_side != sides.c.side)  # NULL (undecided) matches neither
    matching = (
        select(Match.id)
        .join(sides, sides.c.match_id == Match.id)
        .join(Event, Event.id == Match.event_id)
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(matching.subquery())) or 0
    rows = db.execute(
        select(
            Match,
            sides.c.side,
            Event.name,
            Event.discipline,
            Tournament.id,
            Tournament.name,
            Source.attribution,
            IngestRun.started_at,
        )
        .join(sides, sides.c.match_id == Match.id)
        .join(Event, Event.id == Match.event_id)
        .join(Tournament, Tournament.id == Event.tournament_id)
        .join(RawRecordRevision, RawRecordRevision.id == Match.normalized_from_revision_id)
        .join(IngestRun, IngestRun.id == RawRecordRevision.last_seen_run_id)
        .join(Source, Source.id == IngestRun.source_id)
        .where(*filters)
        .order_by(Match.played_on.desc().nulls_last(), Match.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    people, games = _people_and_games(db, [r[0].id for r in rows])

    items: list[PlayerMatch] = []
    for m, side, event, event_discipline, t_id, t_name, attribution, retrieved in rows:
        other = 2 if side == 1 else 1
        items.append(
            PlayerMatch(
                id=m.id,
                played_on=m.played_on,
                tournament=TournamentRef(id=t_id, name=t_name),
                event=event,
                discipline=event_discipline,
                round=m.round,
                status=m.status,
                result=_result(m.winner_side, side),
                games=[(a, b) if side == 1 else (b, a) for a, b in games[m.id]],
                partners=[p for p in people[(m.id, side)] if p.id != player.id],
                opponents=people[(m.id, other)],
                source=attribution,
                retrieved_at=retrieved,
            )
        )
    return MatchPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/tournaments/{tournament_id}")
def tournament_detail(db: DB, tournament_id: int) -> TournamentDetail:
    t = db.get(Tournament, tournament_id)
    if t is None:
        raise HTTPException(404, "no such tournament")
    events = db.execute(
        select(Event.name, Event.discipline, func.count(Match.id))
        .join(Match, Match.event_id == Event.id)
        .where(Event.tournament_id == tournament_id, Event.redistributable)
        .group_by(Event.id)
        .order_by(Event.name)
    ).all()
    if not events:
        raise HTTPException(404, "no such tournament")  # also hides junior-only tournaments
    source = db.get(Source, t.source_id)
    return TournamentDetail(
        id=t.id,
        name=t.name,
        organiser=t.organiser,
        location=t.location,
        start_date=t.start_date,
        end_date=t.end_date,
        events=[EventSummary(name=n, discipline=d, matches=c) for n, d, c in events],
        source=source.attribution if source else t.source_id,
        source_id=t.source_id,
        import_state=_import_states(db, [t]).get(t.id),
    )


def _visible_tournaments() -> Select[int, int, int]:
    """(tournament_id, visible events, visible matches) for tournaments with anything to show."""
    return (
        select(
            Event.tournament_id,
            func.count(func.distinct(Event.id)).label("events"),
            func.count(Match.id).label("matches"),
        )
        .join(Match, Match.event_id == Event.id)
        .where(Match.id.in_(_visible_matches()))
        .group_by(Event.tournament_id)
    )


@router.get("/tournaments")
def list_tournaments(
    db: DB,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    year: int | None = Query(None, ge=1900, le=2100),
    location: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    source: str | None = Query(None, max_length=64),
    discipline: Literal["MS", "WS", "MD", "WD", "XD"] | None = None,
    sort: Literal["newest", "oldest", "matches"] = "newest",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TournamentPage:
    """Tournaments with at least one served match, newest first. Filters combine with AND;
    `discipline` keeps tournaments with a served match in it."""
    visible_matches = _visible_matches()
    if discipline:
        visible_matches = visible_matches.where(Event.discipline == discipline)
    visible = (
        select(
            Event.tournament_id,
            func.count(func.distinct(Event.id)).label("events"),
            func.count(Match.id).label("matches"),
        )
        .join(Match, Match.event_id == Event.id)
        .where(Match.id.in_(visible_matches))
        .group_by(Event.tournament_id)
        .subquery()
    )
    query = (
        select(Tournament, visible.c.events, visible.c.matches, Source.attribution)
        .join(visible, visible.c.tournament_id == Tournament.id)
        .join(Source, Source.id == Tournament.source_id)
    )
    if q:
        query = query.where(Tournament.name.ilike(f"%{q}%"))
    if year is not None:
        query = query.where(func.extract("year", Tournament.start_date) == year)
    if location:
        query = query.where(Tournament.location.ilike(f"%{location}%"))
    if source:
        query = query.where(Tournament.source_id == source)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(
            *{
                "newest": (Tournament.start_date.desc().nulls_last(), Tournament.id.desc()),
                "oldest": (Tournament.start_date.asc().nulls_last(), Tournament.id),
                "matches": (visible.c.matches.desc(), Tournament.id.desc()),
            }[sort]
        )
        .limit(limit)
        .offset(offset)
    ).all()
    states = _import_states(db, [t for t, *_ in rows])
    items = [
        TournamentSummary(
            id=t.id,
            import_state=states.get(t.id),
            name=t.name,
            source_id=t.source_id,
            start_date=t.start_date,
            end_date=t.end_date,
            location=t.location,
            organiser=t.organiser,
            events=e,
            matches=m,
            source=a,
        )
        for t, e, m, a in rows
    ]
    return TournamentPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/tournaments/{tournament_id}/matches")
def tournament_matches(
    db: DB,
    tournament_id: int,
    event: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TournamentMatchPage:
    """Served matches of one tournament, by day, event and round."""
    filters: list[ColumnElement[bool]] = [
        Event.tournament_id == tournament_id,
        Match.id.in_(_visible_matches()),
    ]
    if event:
        filters.append(Event.name == event)
    base = select(Match.id).join(Event, Event.id == Match.event_id).where(*filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    if total == 0 and not db.scalar(
        select(func.count()).select_from(
            _visible_tournaments().where(Event.tournament_id == tournament_id).subquery()
        )
    ):
        raise HTTPException(404, "no such tournament")  # also hides junior-only tournaments
    rows = db.execute(
        select(Match, Event.name, Event.discipline)
        .join(Event, Event.id == Match.event_id)
        .where(*filters)
        .order_by(Match.played_on.nulls_last(), Event.name, Match.id)  # ids follow source order
        .limit(limit)
        .offset(offset)
    ).all()
    people, games = _people_and_games(db, [m.id for m, _, _ in rows])
    items = [
        TournamentMatch(
            id=m.id,
            played_on=m.played_on,
            event=name,
            discipline=discipline,
            round=m.round,
            status=m.status,
            winner_side=m.winner_side,
            games=games[m.id],
            side1=people[(m.id, 1)],
            side2=people[(m.id, 2)],
        )
        for m, name, discipline in rows
    ]
    return TournamentMatchPage(items=items, total=total, limit=limit, offset=offset)


# Known limits per provider: descriptive text, shown beside the derived status.
_LIMITATIONS: dict[str, list[str]] = {
    "tournamentsoftware_ba": [
        "The portal's own listing reaches back about six months; older tournaments arrive via "
        "the global search.",
        "Some tournaments need a login, and international events mirrored here publish no matches.",
    ],
    "tournamentsoftware": [
        "Its badminton search also returns some other sports; their match pages do not parse and "
        "nothing is imported from them.",
        "Tournaments owned by regional portals we are not authorised for are not imported.",
    ],
    "tournamentsoftware_bnz": [
        "Badminton New Zealand's own portal (authorised 2026-11-13). Tournaments behind a login "
        "are not imported.",
    ],
    "bwf": ["Authorised; waiting for BWF's technical access method (API, feed or allowlist)."],
    "tournamentsoftware_bwf": ["Authorised; needs provider-issued login credentials."],
}


def _status(source_id: str, stored: int, recent_runs: list[str]) -> ProviderStatus:
    """From what has actually happened, not from what is configured. `recent_runs` is newest
    first; one tournament that fails (another sport, a removed page) is not an outage."""
    from scout.ingest.operations import OPERATIONS

    if len(recent_runs) >= 3 and "succeeded" not in recent_runs[:10]:
        return "source_error"
    if stored > 0:
        return "connected_importing"
    if any(op.source_id == source_id for op in OPERATIONS.values()):
        return "partially_validated"
    return "pending_access"  # authorised; waiting on the provider's access method or credentials


@router.get("/coverage")
def coverage(db: DB) -> Coverage:
    """Per provider: derived status and counts. Public counts include served data only."""
    visible = select(_visible_matches().subquery().c.id)
    # every authorised provider with hosts, in registry order: the global integration tracker
    listed = [sid for sid, rights in SOURCES.items() if rights.hosts]
    sources = {s.id: s for s in db.scalars(select(Source).where(Source.id.in_(listed)))}

    def per_source(query: Any) -> dict[str, Any]:
        """{source_id: value} from rows keyed by their first column (tuples when several)."""
        rows: list[Any] = list(db.execute(query).all())
        return {r[0]: tuple(r[1:]) if len(r) > 2 else r[1] for r in rows}

    by_match = (
        select(Tournament.source_id)
        .join(Event, Event.tournament_id == Tournament.id)
        .join(Match, Match.event_id == Event.id)
    )
    stored = per_source(by_match.add_columns(func.count(Match.id)).group_by(Tournament.source_id))
    public = per_source(
        by_match.add_columns(
            func.count(func.distinct(Tournament.id)),
            func.count(Match.id),
            func.min(Match.played_on),
            func.max(Match.played_on),
        )
        .where(Match.id.in_(visible))
        .group_by(Tournament.source_id)
    )
    people = (
        select(Tournament.source_id, PlayerLink.player_id)
        .join(Event, Event.tournament_id == Tournament.id)
        .join(Match, Match.event_id == Event.id)
        .join(MatchSide, MatchSide.match_id == Match.id)
        .join(MatchSidePlayer, MatchSidePlayer.match_side_id == MatchSide.id)
        .join(PlayerLink, PlayerLink.source_player_id == MatchSidePlayer.source_player_id)
        .where(Match.id.in_(visible))
        .distinct()
        .subquery()
    )
    players = per_source(
        select(people.c.source_id, func.count(people.c.player_id)).group_by(people.c.source_id)
    )
    discovered = per_source(
        select(TournamentDiscovery.owner_source, func.count())
        .where(TournamentDiscovery.owner_source.is_not(None))
        .group_by(TournamentDiscovery.owner_source)
    )
    queued_states = ["new", "partial", "not_finished"]
    queued = per_source(
        select(TournamentDiscovery.owner_source, func.count())
        .where(TournamentDiscovery.status.in_(queued_states))
        .group_by(TournamentDiscovery.owner_source)
    )
    syncs = {
        sid: sync
        for sid in sources
        if (
            sync := db.scalars(
                select(SyncRun)
                .where(SyncRun.source_id == sid, SyncRun.status != "running")
                .order_by(SyncRun.started_at.desc())
                .limit(1)
            ).first()
        )
    }
    finished = db.scalar(
        select(func.max(SyncRun.finished_at)).where(SyncRun.status.in_(["succeeded", "incomplete"]))
    )
    # the scheduler's latest plan; a manual run without --every does not erase it
    planned = db.scalar(
        select(SyncRun.next_run_at)
        .where(SyncRun.next_run_at.is_not(None))
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )
    runs = {
        sid: list(
            db.scalars(
                select(IngestRun.status)
                .where(IngestRun.source_id == sid, IngestRun.status != "running")
                .order_by(IngestRun.started_at.desc())
                .limit(10)
            )
        )
        for sid in sources
    }
    retrieved = per_source(
        select(IngestRun.source_id, func.max(IngestRun.finished_at))
        .where(IngestRun.status == "succeeded")
        .group_by(IngestRun.source_id)
    )
    providers: list[ProviderCoverage] = []
    for sid in listed:
        limitations = _LIMITATIONS.get(sid, [])
        if sid not in sources:
            continue
        t, m, lo, hi = public.get(sid, (0, 0, None, None))
        providers.append(
            ProviderCoverage(
                source_id=sid,
                name=sources[sid].name,
                attribution=sources[sid].attribution,
                status=_status(sid, stored.get(sid, 0), runs[sid]),
                limitations=limitations,
                discovered_tournaments=discovered.get(sid, 0),
                public_tournaments=t,
                public_matches=m,
                public_players=players.get(sid, 0),
                first_played=lo,
                last_played=hi,
                last_retrieved_at=retrieved.get(sid),
                awaiting_import=queued.get(sid, 0),
                last_sync_at=syncs[sid].finished_at if sid in syncs else None,
                last_sync_status=syncs[sid].status if sid in syncs else None,
            )
        )
    distinct_players = db.scalar(select(func.count(func.distinct(people.c.player_id)))) or 0
    return Coverage(
        providers=providers,
        last_sync_at=finished,
        next_sync_at=planned,  # may be in the past: the schedule is overdue
        # every queued listing, routed or not (None key: owner not yet checked)
        awaiting_import=sum(queued.values()),
        excluded=[]
        if scout.privacy.PUBLISH_RESTRICTED_EVENTS  # ADR-0010: everything stored is served
        else [
            "Junior events (players under 18): minors' data is not published (ADR-0009).",
            "Para-badminton classes: a sport class is health data and is not published.",
            "Events whose category cannot be recognised as adult are withheld until classified.",
        ],
        # over every served record, not only the providers listed above
        public_tournaments=sum(t for t, *_ in public.values()),
        public_matches=sum(m for _, m, *_ in public.values()),
        public_players=distinct_players,
        last_retrieved_at=max(
            (p.last_retrieved_at for p in providers if p.last_retrieved_at), default=None
        ),
    )
