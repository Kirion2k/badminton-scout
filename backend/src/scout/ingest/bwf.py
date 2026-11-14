"""BWF tournament results, normalised into Mynton's match model (no network here).

The shapes are those of the BWF Fansite's own read API as used by a published acquisition
script (github.com/SahilMotyar/badminton-elo, fetch_bwf.py and badminton/bwf.py, read
2026-11-14): `vue-tournaments-search` for the tournament index and `vue-tournament-matches`
for one tournament's matches. No operation for that API is registered: its host
(extranet-lv.bwfbadminton.com) is outside the recorded BWF scope and answers automated clients
with a Cloudflare challenge (docs/bwf-access-request.md). This module turns such a payload,
however it is lawfully obtained, into stored records with full provenance.

Ported from the published code: the by_time/by_court flattening with match-id dedupe, the
discipline and qualification parse, the per-game score parse and the BWF player ids. Changed
for Mynton: walkovers and retirements are kept and labelled instead of dropped or passed off as
completed matches, players are keyed by BWF id (never by name), and every match is a revisioned
raw record keyed by its BWF match id (ADR-0005).
"""

import re
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.ingest.raw import record_payload
from scout.ingest.tournamentsoftware import (
    NormalizedMatch,
    PlayerRef,
    Rejection,
    Status,
    clean_name,
    record_issue,
    write_match,
)
from scout.models import IngestRun, Match, RawRecord, Tournament

DISCIPLINES = ("MS", "WS", "MD", "WD", "XD")
_SPAN = re.compile(r"<span>(\d+)</span>")


class BwfTournament(BaseModel):
    """One entry of the tournament index (vue-tournaments-search results.data)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    name: str
    start_date: str | None = None  # "YYYY-MM-DD hh:mm:ss"
    end_date: str | None = None
    location: str | None = None
    category: str | None = None


class BwfPlayer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    name_display: str | None = None
    nationality: str | None = None


class BwfMatch(BaseModel):
    """One match of vue-tournament-matches, after flattening."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    draw_name: str | None = None  # "MS", "MS - Qualification"
    round_name: str | None = None
    winner: int | None = None  # 1 or 2
    team1Score: str | None = None  # the API's own field names
    team2Score: str | None = None
    start_time: int | None = None  # unix seconds
    t1p1_detail: BwfPlayer | None = None
    t1p2_detail: BwfPlayer | None = None
    t2p1_detail: BwfPlayer | None = None
    t2p2_detail: BwfPlayer | None = None


def _dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def flatten(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every match once: older tournaments list results.by_time.time_group, newer ones only
    results.by_court ({section: {key: match}}). Both are read, deduped on match id."""
    results = _dict(data.get("results"))
    group: object = _dict(results.get("by_time")).get("time_group")
    candidates: list[object] = list(cast(list[object], group)) if isinstance(group, list) else []
    for section in _dict(results.get("by_court")).values():
        candidates.extend(_dict(section).values())
    out: list[dict[str, Any]] = []
    seen: set[object] = set()
    for m in map(_dict, candidates):
        if m.get("id") is not None and m["id"] not in seen:
            seen.add(m["id"])
            out.append(m)
    return out


def discipline(draw_name: str | None) -> tuple[str | None, bool]:
    """'MS - Qualification' -> ('MS', True); 'XD' -> ('XD', False); anything else -> None."""
    if not draw_name or not draw_name.strip():
        return None, False
    head = draw_name.split()[0].split("-")[0].strip().upper()
    if head not in DISCIPLINES:
        return None, False
    return head, "qual" in draw_name.lower()


def games(team1: str | None, team2: str | None) -> tuple[tuple[int, int], ...] | None:
    """Per-game points from the two score fragments; None when they disagree in length."""
    a = [int(x) for x in _SPAN.findall(team1 or "")]
    b = [int(x) for x in _SPAN.findall(team2 or "")]
    if len(a) != len(b):
        return None
    return tuple(zip(a, b, strict=True))


def finished(game: tuple[int, int]) -> bool:
    """A game ends at 21 with a two-point lead, or at 30 (Laws of Badminton, 21-point scoring)."""
    hi, lo = max(game), min(game)
    return hi == 30 or (hi >= 21 and hi - lo >= 2)


def status_of(winner: int | None, played: tuple[tuple[int, int], ...]) -> Status:
    """No winner: not played. A winner without games: walkover. A winner whose last game never
    reached a legal end: retired. Otherwise completed."""
    if winner not in (1, 2):
        return "not_played"
    if not played:
        return "walkover"
    return "completed" if finished(played[-1]) else "retired"


def _side(m: BwfMatch, team: int) -> tuple[PlayerRef, ...]:
    slots = (m.t1p1_detail, m.t1p2_detail) if team == 1 else (m.t2p1_detail, m.t2p2_detail)
    # keyed by BWF player id: two people with one display name stay two people
    return tuple(
        PlayerRef(
            source_key=f"bwf:{p.id}",
            display_name=clean_name(p.name_display or "") or f"BWF player {p.id}",
        )
        for p in slots
        if p is not None and p.id
    )


def normalize(m: BwfMatch, t: BwfTournament) -> NormalizedMatch | Rejection:
    code, qualification = discipline(m.draw_name)
    if code is None:
        return Rejection("unknown_discipline", m.draw_name or "")
    side1, side2 = _side(m, 1), _side(m, 2)
    need = 2 if code in ("MD", "WD", "XD") else 1
    if len(side1) != need or len(side2) != need:
        return Rejection("incomplete_sides", f"{len(side1)} v {len(side2)} players in {code}")
    played = games(m.team1Score, m.team2Score)
    if played is None:
        return Rejection("malformed_score", "game counts differ between the sides")
    if m.start_time is None:
        return Rejection("no_date", "match has no start time")
    status = status_of(m.winner, played)
    round_ = (m.round_name or "").strip() or None
    return NormalizedMatch(
        tournament_key=str(t.id),
        draw_key=f"draw|{(m.draw_name or code).strip()}",
        event_name=(m.draw_name or code).strip(),
        discipline=code,
        round=f"Qualification {round_}" if qualification and round_ else round_,
        played_on=datetime.fromtimestamp(m.start_time, UTC).date(),
        status=status,
        winner_side=m.winner if status != "not_played" else None,
        games=played,
        duration_minutes=None,
        court=None,
        sides=(side1, side2),
    )


def _day(value: str | None) -> date | None:
    return (
        date.fromisoformat(value[:10]) if value and re.match(r"\d{4}-\d{2}-\d{2}", value) else None
    )


def ingest_tournament(
    session: Session, run: IngestRun, index_entry: Mapping[str, Any], payload: Mapping[str, Any]
) -> Counter[str]:
    """Store one tournament and its matches as revisioned raw records, then normalise them.

    Idempotent: an unchanged match is a no-op, a corrected one becomes a new revision of the
    same record (keyed by BWF match id, never by score). `run.source_id` names where the payload
    came from, so a historical third-party copy is never labelled as direct BWF data.
    """
    t = BwfTournament.model_validate(index_entry)
    counts: Counter[str] = Counter()
    key = f"tournament|{t.id}"
    counts[f"tournament_{record_payload(session, run, key, dict(index_entry))}"] += 1
    record = session.scalars(
        select(RawRecord).filter_by(source_id=run.source_id, source_record_key=key)
    ).one()
    tournament = session.scalar(
        select(Tournament).filter_by(source_id=run.source_id, source_key=str(t.id))
    ) or Tournament(source_id=run.source_id, source_key=str(t.id))
    tournament.name, tournament.raw_record_id = " ".join(t.name.split()), record.id
    tournament.location = (t.location or "").strip() or None
    tournament.start_date, tournament.end_date = _day(t.start_date), _day(t.end_date)
    session.add(tournament)
    session.flush()

    for raw in flatten(payload):
        m = BwfMatch.model_validate(raw)
        mkey = f"match|{m.id}"
        outcome = record_payload(session, run, mkey, raw)
        counts[outcome] += 1
        if outcome == "unchanged":
            continue
        rec = session.scalars(
            select(RawRecord).filter_by(source_id=run.source_id, source_record_key=mkey)
        ).one()
        normalized = normalize(m, t)
        if isinstance(normalized, Rejection):
            existing = session.scalar(select(Match).filter_by(raw_record_id=rec.id))
            if existing:
                session.delete(existing)
            record_issue(session, run, rec.id, normalized.kind, {"detail": normalized.detail})
            counts[f"rejected:{normalized.kind}"] += 1
            continue
        write_match(session, run.source_id, rec, normalized)
        counts["normalized"] += 1
        counts[f"status:{normalized.status}"] += 1
    session.flush()
    return counts
