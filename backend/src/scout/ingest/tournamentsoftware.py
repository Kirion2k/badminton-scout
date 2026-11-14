"""Tournament Software matches -> raw revisions -> badminton domain tables (ADR-0003, ADR-0005)."""

import re
import urllib.parse
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scout.config import get_settings
from scout.ingest.operations import TsMatchRow, TsTournament, ts_match_key, ts_tournament_key
from scout.ingest.raw import content_hash, record_payload
from scout.models import (
    AppSetting,
    Event,
    Game,
    IdentityDecision,
    IngestIssue,
    IngestRun,
    Match,
    MatchSide,
    MatchSidePlayer,
    Player,
    PlayerLink,
    RawRecord,
    SourcePlayer,
    Tournament,
)
from scout.privacy import (
    canonical_event,
    is_redistributable_event,
    key_fingerprint,
    minimise_h2h,
)
from scout.sources import SOURCES

Status = Literal["completed", "walkover", "retired", "disqualified", "winner_only", "not_played"]

# event-name prefixes; junior events use B/G for boys/girls
_DISCIPLINES = {
    "MS": "MS", "BS": "MS", "WS": "WS", "GS": "WS",
    "MD": "MD", "BD": "MD", "WD": "WD", "GD": "WD", "XD": "XD", "MX": "XD",
}  # fmt: skip


# match messages seen on Tournament Software, and what they mean. Extend only from real pages.
_MESSAGES: dict[str, Status] = {
    "walkover": "walkover",
    "retired": "retired",  # seen 2026-11-12
    "cancelled": "not_played",  # seen 2026-11-12
    "abgesagt": "not_played",  # German "cancelled", dbv.turnier.de, seen 2026-11-13
    "opgave": "retired",  # Dutch "retired", badvla., seen 2026-11-13
    # a winner by disqualification; games played before it are kept as recorded (seen 2026-11-13)
    "disqualified": "disqualified",
}


@dataclass(frozen=True)
class PlayerRef:
    source_key: str
    display_name: str


@dataclass(frozen=True)
class NormalizedMatch:
    tournament_key: str
    draw_key: str
    event_name: str
    discipline: str | None
    round: str | None
    played_on: date
    status: Status
    winner_side: int | None
    games: tuple[tuple[int, int], ...]
    duration_minutes: int | None
    court: str | None
    sides: tuple[tuple[PlayerRef, ...], tuple[PlayerRef, ...]]


@dataclass(frozen=True)
class Rejection:
    kind: str
    detail: str


def discipline_of(event: str) -> str | None:
    """From the prefix ("MS C", "GS U11", "Đơn Nam N3"), else from words ("Mon U13 Boys Sgls")."""
    words = canonical_event(event).split()
    if words and (prefix := _DISCIPLINES.get(words[0].upper())):
        return prefix
    text = event.lower()
    singles = re.search(r"\b(sgls|singles)\b", text)
    doubles = re.search(r"\b(dbls|doubles)\b", text)
    if not (singles or doubles) or (singles and doubles):
        return None
    if re.search(r"\bmixed\b", text):
        return "XD" if doubles else None
    men = re.search(r"\b(boys|men|mens|men's)\b", text)
    women = re.search(r"\b(girls|women|womens|women's|ladies)\b", text)
    if bool(men) == bool(women):
        return None
    return ("M" if men else "W") + ("S" if singles else "D")


def _query(href: str, name: str) -> str | None:
    found = re.search(rf"[?&]{name}=([^&#]+)", href)
    return found.group(1) if found else None


_SEED = re.compile(r"\s*\[\d+(?:/\d+)?\]$")


def clean_name(name: str) -> str:
    """The name without the event seeding the site appends ("Ann LEE [3/4]" -> "Ann LEE")."""
    return _SEED.sub("", " ".join(name.split()))


def _player_refs(row: TsMatchRow, side: int, tournament: str) -> tuple[PlayerRef, ...]:
    """Prefer the association member id (stable across tournaments) from the head-to-head link,
    else the tournament-scoped player id, which deliberately never links across tournaments."""
    ids, names = (row.side1_ids, row.side1_names) if side == 1 else (row.side2_ids, row.side2_names)
    org = _query(row.h2h or "", "OrganizationCode")
    refs: list[PlayerRef] = []
    for position, (player_id, name) in enumerate(zip(ids, names, strict=True), start=1):
        member = _query(row.h2h or "", f"T{side}P{position}MemberID")
        # a placeholder member id ("-", "...") identifies nobody: tournament-scoped instead
        real = member and re.search(r"[0-9A-Za-z]", urllib.parse.unquote_plus(member))
        key = f"member:{org}/{member}" if org and real else f"tplayer:{tournament}/{player_id}"
        refs.append(PlayerRef(key.lower(), clean_name(name)))
    return tuple(refs)


def identifier_key(session: Session) -> str | None:
    """The configured identifier key, checked against the fingerprint stored the first time it
    was used: a changed key would re-key every tokenised member and split their players."""
    secret = get_settings().identifier_key
    if secret is None:
        return None
    key = secret.get_secret_value()
    stored = session.get(AppSetting, "identifier_key_fingerprint")
    if stored is None:
        session.add(AppSetting(name="identifier_key_fingerprint", value=key_fingerprint(key)))
        session.flush()
    elif stored.value != key_fingerprint(key):
        raise RuntimeError("SCOUT_IDENTIFIER_KEY differs from the key used before: restore it")
    return key


def _duration_and_court(info: str | None) -> tuple[int | None, str | None]:
    if not info:
        return None, None
    parts = [p.strip() for p in info.split("|")]
    duration = None
    if parts[0].startswith("Duration:"):
        h = re.search(r"(\d+)h", parts[0])
        m = re.search(r"(\d+)m", parts[0])
        duration = (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
        parts = parts[1:]
    return duration, (parts[0] if parts else None)


def normalize(
    row: TsMatchRow, played_on: date, hosts: frozenset[str] = frozenset()
) -> NormalizedMatch | Rejection:
    host = urllib.parse.urlsplit(row.draw_href).hostname or ""
    if hosts and host not in hosts:
        # a redirect to another portal would put its data here: never under the wrong source
        return Rejection("foreign_host", f"draw link on {host}")
    tournament = _query(row.draw_href, "id")
    draw = _query(row.draw_href, "draw")
    if not tournament or not draw:
        return Rejection("missing_identifiers", "draw link has no tournament or draw id")
    shape = (len(row.side1_ids), len(row.side2_ids))
    if shape == (0, 0):
        return Rejection("unfilled_slot", "draw slot with no players yet")
    if 0 in shape:
        # one side empty: a bye when nothing was played, else a player shown without a profile
        # link (seen in junior events), which the recipe cannot read: kept raw, not guessed
        kind = "unlinked_player" if row.points or row.message == "Walkover" else "bye"
        return Rejection(kind, f"players per side {shape}")
    if shape not in ((1, 1), (2, 2)):
        return Rejection("unexpected_sides", f"players per side {shape}")
    if len(row.side1_names) != shape[0] or len(row.side2_names) != shape[1]:
        return Rejection("names_mismatch", "player names don't line up with player ids")
    if not all(p.strip().isdigit() for p in row.points) or len(row.points) % 2:
        return Rejection("malformed_score", f"{len(row.points)} score cells")

    discipline = discipline_of(row.event)
    if discipline and (discipline[1] == "S") != (shape == (1, 1)):
        return Rejection("discipline_mismatch", f"{row.event!r} with {shape} players per side")

    points = [int(p) for p in row.points]
    games = tuple((points[i], points[i + 1]) for i in range(0, len(points), 2))
    winners = [i + 1 for i, classes in enumerate(row.row_classes[:2]) if "has-won" in classes]
    message = (row.message or "").strip().lower()
    if message and message not in _MESSAGES:
        # an outcome we have not seen yet: reject and look, rather than guess what it means
        return Rejection("unknown_message", f"match message {row.message!r}")
    status: Status = _MESSAGES.get(message) or ("completed" if games else "not_played")
    if message and status == "not_played" and len(winners) == 1:
        # cancelled, yet one side advanced: a walkover. German portals add a nominal 21-0 21-0,
        # which was never played, so no games are kept (seen on ba., dbv., cbbd., 2026-11-13)
        status, games = "walkover", ()
    if not message and status == "not_played" and len(winners) == 1:
        # the source marks a winner but publishes no score: a verified result, score unavailable
        status = "winner_only"
    if status == "not_played" and winners:
        return Rejection("winner_without_play", "a match with no games or outcome marks a winner")
    if status != "not_played" and len(winners) != 1:
        return Rejection("no_winner", f"{status} match marks {len(winners)} winners")
    if status == "walkover" and games:
        return Rejection("walkover_with_score", "walkover carries game scores")
    if status == "completed" and any(max(a, b) < 11 for a, b in games):
        # every common badminton game runs to 11, 15, 21 or 30: a 6-4 set is another sport
        return Rejection("implausible_badminton_score", f"games {list(games)}")
    if status == "completed":
        won = [sum(a > b for a, b in games), sum(b > a for a, b in games)]
        if won[winners[0] - 1] <= won[2 - winners[0]]:
            return Rejection("winner_disagrees_with_score", f"games won {won}, winner {winners[0]}")

    duration, court = _duration_and_court(row.info)
    return NormalizedMatch(
        tournament_key=tournament.lower(),
        draw_key=draw,
        event_name=row.event.strip(),
        discipline=discipline,
        round=row.round,
        played_on=played_on,
        status=status,
        winner_side=winners[0] if len(winners) == 1 else None,
        games=games,
        duration_minutes=duration,
        court=court,
        sides=(_player_refs(row, 1, tournament), _player_refs(row, 2, tournament)),
    )


def get_or_create_source_player(session: Session, source_id: str, ref: PlayerRef) -> SourcePlayer:
    found = session.scalar(
        select(SourcePlayer).filter_by(source_id=source_id, source_key=ref.source_key)
    )
    if found:
        return found
    sp = SourcePlayer(source_id=source_id, source_key=ref.source_key, display_name=ref.display_name)
    player = Player(display_name=ref.display_name)
    session.add_all([sp, player])
    session.flush()
    # exact identity only: a new source identity gets its own canonical player (ADR-0003)
    decision = IdentityDecision(
        action="link",
        after={"source_player_id": sp.id, "player_id": player.id},
        reason="new source identity",
        decided_by="system:exact",
    )
    session.add(decision)
    session.flush()
    session.add(PlayerLink(source_player_id=sp.id, player_id=player.id, decision_id=decision.id))
    return sp


def write_match(session: Session, source_id: str, record: RawRecord, m: NormalizedMatch) -> None:
    tournament = session.scalar(
        select(Tournament).filter_by(source_id=source_id, source_key=m.tournament_key)
    ) or Tournament(source_id=source_id, source_key=m.tournament_key)
    session.add(tournament)
    session.flush()
    event = session.scalar(
        select(Event).filter_by(tournament_id=tournament.id, source_key=m.draw_key)
    ) or Event(tournament_id=tournament.id, source_key=m.draw_key)
    event.name, event.discipline = m.event_name, m.discipline
    event.redistributable = is_redistributable_event(m.event_name, m.discipline)
    session.add(event)
    session.flush()

    if record.current_revision_id is None:
        raise RuntimeError(f"raw record {record.id} has no current revision")
    match = session.scalar(select(Match).filter_by(raw_record_id=record.id)) or Match(
        raw_record_id=record.id
    )
    match.normalized_from_revision_id = record.current_revision_id
    match.event_id = event.id
    match.round, match.played_on, match.status = m.round, m.played_on, m.status
    match.winner_side, match.duration_minutes, match.court = (
        m.winner_side,
        m.duration_minutes,
        m.court,
    )
    session.add(match)
    session.flush()
    # a new revision replaces the derived rows; the raw revisions keep the history
    session.execute(delete(MatchSide).where(MatchSide.match_id == match.id))
    session.execute(delete(Game).where(Game.match_id == match.id))
    for side_no, refs in enumerate(m.sides, start=1):
        side = MatchSide(match_id=match.id, side=side_no)
        session.add(side)
        session.flush()
        for position, ref in enumerate(refs, start=1):
            sp = get_or_create_source_player(session, source_id, ref)
            session.add(
                MatchSidePlayer(match_side_id=side.id, position=position, source_player_id=sp.id)
            )
    for number, (a, b) in enumerate(m.games, start=1):
        session.add(Game(match_id=match.id, number=number, side1_points=a, side2_points=b))
    session.flush()


def ingest_rows(
    session: Session,
    run: IngestRun,
    played_on: date,
    items: Sequence[TsMatchRow],
    rows: Sequence[dict[str, Any]],
    *,
    renormalize: bool = False,
) -> Counter[str]:
    """Store one day's rows and normalize them. Returns outcome counts for the quality report.

    `renormalize` re-applies the current rules to unchanged records too (after a rule change).
    """
    counts: Counter[str] = Counter()
    by_key: dict[str, list[tuple[TsMatchRow, dict[str, Any]]]] = defaultdict(list)
    key = identifier_key(session)
    for item, row in zip(items, rows, strict=True):
        # national-identity member ids never reach storage, in the payload or in a key
        minimal = minimise_h2h(row.get("h2h"), key)
        if minimal != row.get("h2h"):
            if key is None:
                counts["identifier_dropped"] += 1  # no key: kept out, at the cost of identity
            row = row | {"h2h": minimal}
            item = TsMatchRow.model_validate(row)
        by_key[ts_match_key(item)].append((item, row))

    for key, group in by_key.items():
        if len({content_hash(row) for _, row in group}) > 1:
            # two different matches share a locator: store neither, ask a human (ADR-0005)
            session.add(
                IngestIssue(
                    run_id=run.id, kind="key_collision", detail={"key": key, "rows": len(group)}
                )
            )
            counts["key_collision"] += len(group)
            continue
        counts["duplicate_rows"] += len(group) - 1
        item, row = group[0]
        outcome = record_payload(session, run, key, row)
        counts[outcome] += 1
        if outcome == "unchanged" and not renormalize:
            continue  # same revision as last time: normalized (or rejected) then
        record = session.scalars(
            select(RawRecord).filter_by(source_id=run.source_id, source_record_key=key)
        ).one()
        existing = session.scalar(select(Match).filter_by(raw_record_id=record.id))
        normalized = normalize(item, played_on, SOURCES[run.source_id].hosts)
        if isinstance(normalized, Rejection):
            if existing:  # the source's new revision no longer makes a valid match
                session.delete(existing)
            record_issue(session, run, record.id, normalized.kind, {"detail": normalized.detail})
            counts[f"rejected:{normalized.kind}"] += 1
            continue
        write_match(session, run.source_id, record, normalized)
        counts["normalized"] += 1
    counts["missing_from_source"] += _flag_missing(session, run, played_on, items, set(by_key))
    session.flush()
    return counts


def _flag_missing(
    session: Session, run: IngestRun, played_on: date, items: Sequence[TsMatchRow], seen: set[str]
) -> int:
    """Matches we hold for this tournament day that the source no longer lists, for example after
    a partner substitution changed the key. Flagged for review, never deleted."""
    tournaments = {(_query(i.draw_href, "id") or "").lower() for i in items}
    if len(tournaments) != 1:
        return 0
    held = session.execute(
        select(RawRecord.id, RawRecord.source_record_key)
        .join(Match, Match.raw_record_id == RawRecord.id)
        .join(Event, Event.id == Match.event_id)
        .join(Tournament, Tournament.id == Event.tournament_id)
        .where(
            RawRecord.source_id == run.source_id,
            Tournament.source_key == tournaments.pop(),
            Match.played_on == played_on,
        )
    ).all()
    missing = [(rid, key) for rid, key in held if key not in seen]
    for rid, key in missing:
        record_issue(session, run, rid, "missing_from_source", {"key": key})
    return len(missing)


def record_issue(
    session: Session, run: IngestRun, raw_record_id: int, kind: str, detail: dict[str, Any]
) -> None:
    """Record an issue once per record and kind; later runs that see it again add nothing."""
    seen = select(IngestIssue.id).filter_by(raw_record_id=raw_record_id, kind=kind)
    if session.scalar(seen) is None:
        issue = IngestIssue(run_id=run.id, raw_record_id=raw_record_id, kind=kind, detail=detail)
        session.add(issue)


def ingest_tournaments(
    session: Session, run: IngestRun, items: Sequence[TsTournament], rows: Sequence[dict[str, Any]]
) -> Counter[str]:
    """Store tournament listings as revisioned records and keep tournament metadata current."""
    counts: Counter[str] = Counter()
    for item, row in zip(items, rows, strict=True):
        key = ts_tournament_key(item)
        counts[f"tournaments_{record_payload(session, run, key, row)}"] += 1
        record = session.scalars(
            select(RawRecord).filter_by(source_id=run.source_id, source_record_key=key)
        ).one()
        guid = key.split("|", 1)[1]
        t = session.scalar(
            select(Tournament).filter_by(source_id=run.source_id, source_key=guid)
        ) or Tournament(source_id=run.source_id, source_key=guid)
        organiser, _, location = (item.subheading or "").partition("|")
        days = [date.fromisoformat(d[:10]) for d in item.dates if re.match(r"\d{4}-\d{2}-\d{2}", d)]
        t.name, t.raw_record_id = " ".join(item.name.split()), record.id
        t.organiser, t.location = organiser.strip() or None, location.strip() or None
        t.start_date = days[0] if days else None
        t.end_date = days[-1] if days else None
        session.add(t)
    session.flush()
    return counts
