"""Import of bwf-match-data, a third-party compilation of BWF results (source
`bwf_historical_compilation`; owner-attested grant, docs/data-sources.md).

The files are CSVs of names and scores: no match ids and, except for 24 names carrying a
`[player-id]` suffix, no player ids (docs/bwf-historical-import.md). So:

- a tournament is the index entry whose name matches and whose dates contain the match date
  (the index carries BWF's own tournament id); anything else is quarantined, never guessed;
- a player is keyed by the exact name within this dataset (`name:<name>`), or by the BWF id
  in a `[id]` suffix (`bwf:<id>`); no key is ever shared with another source, and no name is
  matched across sources (ADR-0003, ADR-0011);
- a match key is tournament, event, round, date and both sides, never the score (ADR-0005);
  identical repeats are counted once, differing repeats are quarantined as a key collision;
- the status is read from the scoring format, never from the winner alone: "completed" only when
  the winner took the games the format needs and every game ended legally; a match that stopped
  early is "retired"; anything else is quarantined as an irregular score.
"""

import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.ingest.raw import content_hash, record_payload
from scout.ingest.tournamentsoftware import (
    NormalizedMatch,
    PlayerRef,
    Rejection,
    Status,
    record_issue,
    write_match,
)
from scout.models import IngestIssue, IngestRun, Match, RawRecord, Tournament

SOURCE = "bwf_historical_compilation"
DISCIPLINES = ("MS", "WS", "MD", "WD", "XD")
_SUFFIX = re.compile(r"\s*\[(\d+)\]$")
_GAME = re.compile(r"^(\d+)-(\d+)$")


def legal_21(game: tuple[int, int]) -> bool:
    """21-point game: 21 with a two-point lead, or 30 (Laws of Badminton)."""
    hi, lo = max(game), min(game)
    return hi == 30 or (hi >= 21 and hi - lo >= 2)


def legal_11(game: tuple[int, int]) -> bool:
    """11-point game (5x11 trial, 2014-2017): 11 with a two-point lead, capped at 15."""
    hi, lo = max(game), min(game)
    return hi == 15 or (hi >= 11 and hi - lo >= 2)


def scoring_format(games: Sequence[tuple[int, int]]) -> str:
    """'5x11' when every game stays at or under 15 points and one ended as an 11-point game;
    otherwise the standard '3x21'."""
    if all(max(g) <= 15 for g in games) and any(legal_11(g) for g in games):
        return "5x11"
    return "3x21"


def status_of(winner: int, games: Sequence[tuple[int, int]]) -> Status | None:
    """The outcome the scores support, or None when they contradict the recorded winner."""
    fmt = scoring_format(games)
    need, legal = (3, legal_11) if fmt == "5x11" else (2, legal_21)
    if not legal(games[-1]):
        return "retired"  # stopped inside a game
    won = sum(1 for a, b in games if (a > b) == (winner == 1))
    lost = len(games) - won
    if lost >= need or not all(legal(g) for g in games):
        return None  # the recorded loser won the match, or a game ended illegally
    last_won = (games[-1][0] > games[-1][1]) == (winner == 1)
    if won == need and last_won:
        return "completed"  # the match ends the moment the winner takes the games needed
    if won < need:
        return "retired"  # short of the games needed: stopped between games
    return None  # games played after the match was already decided


@dataclass(frozen=True)
class Index:
    """The tournament index, by normalised name."""

    by_name: Mapping[str, Sequence[Mapping[str, Any]]]

    @staticmethod
    def load(entries: Iterable[Mapping[str, Any]]) -> "Index":
        by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for t in entries:
            by_name[_norm(str(t.get("name") or ""))].append(t)
        return Index(by_name)

    def resolve(self, name: str, played: date) -> Mapping[str, Any] | None:
        hits = [
            t
            for t in self.by_name.get(_norm(name), [])
            if _day(t.get("start_date")) <= played <= _day(t.get("end_date"), default=date.max)
        ]
        return hits[0] if len(hits) == 1 else None


def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


def _day(value: object, default: date = date.min) -> date:
    text = str(value or "")
    return date.fromisoformat(text[:10]) if re.match(r"\d{4}-\d{2}-\d{2}", text) else default


def _player(name: str) -> PlayerRef:
    name = " ".join(name.split())
    suffix = _SUFFIX.search(name)
    if suffix:  # the publisher's disambiguation: the BWF player id itself
        return PlayerRef(source_key=f"bwf:{suffix.group(1)}", display_name=_SUFFIX.sub("", name))
    return PlayerRef(source_key=f"name:{name}", display_name=name)


def event_of(row: Mapping[str, str]) -> str:
    qualification = (row.get("round") or "").startswith("Q ")
    return f"{row['discipline']} Qualification" if qualification else row["discipline"]


def match_key(tournament_id: int, row: Mapping[str, str]) -> str:
    sides = sorted(" / ".join(sorted(row[s].split(" / "))) for s in ("team1", "team2"))
    rnd = (row.get("round") or "").strip()
    return f"match|{tournament_id}|{event_of(row)}|{rnd}|{row['date']}|{'|'.join(sides)}"


def normalize(row: Mapping[str, str], tournament_id: int) -> NormalizedMatch | Rejection:
    disc = (row.get("discipline") or "").strip().upper()
    if disc not in DISCIPLINES:
        return Rejection("unknown_discipline", disc)
    try:
        played = date.fromisoformat(row["date"])
    except (KeyError, ValueError):
        return Rejection("no_date", row.get("date") or "")
    sides = tuple(
        tuple(_player(n) for n in (row.get(s) or "").split(" / ") if n.strip())
        for s in ("team1", "team2")
    )
    need = 2 if disc in ("MD", "WD", "XD") else 1
    if any(len(side) != need for side in sides):
        return Rejection("incomplete_sides", f"{[len(s) for s in sides]} players in {disc}")
    parts = [_GAME.match(g) for g in (row.get("score") or "").split()]
    if not parts or any(p is None for p in parts):
        return Rejection("malformed_score", "score is empty or not N-N games")
    games = tuple((int(p.group(1)), int(p.group(2))) for p in parts if p)
    if row.get("winner") not in ("1", "2"):
        return Rejection("no_winner", row.get("winner") or "")
    winner = int(row["winner"])
    status = status_of(winner, games)
    if status is None:
        return Rejection("irregular_score", "the games do not support the recorded winner")
    rnd = (row.get("round") or "").strip() or None
    event = event_of(row)
    return NormalizedMatch(
        tournament_key=str(tournament_id),
        draw_key=f"draw|{event}",
        event_name=event,
        discipline=disc,
        round=rnd,
        played_on=played,
        status=status,
        winner_side=winner,
        games=games,
        duration_minutes=None,
        court=None,
        sides=(sides[0], sides[1]),
    )


def _tournament(session: Session, run: IngestRun, entry: Mapping[str, Any]) -> None:
    key = f"tournament|{entry['id']}"
    record_payload(session, run, key, dict(entry))
    record = session.scalars(
        select(RawRecord).filter_by(source_id=run.source_id, source_record_key=key)
    ).one()
    t = session.scalar(
        select(Tournament).filter_by(source_id=run.source_id, source_key=str(entry["id"]))
    ) or Tournament(source_id=run.source_id, source_key=str(entry["id"]))
    t.name = " ".join(str(entry.get("name") or "").split()) or None
    t.raw_record_id = record.id
    t.location = (str(entry.get("location") or "")).strip() or None
    t.start_date = _day(entry.get("start_date"), date.min)
    t.end_date = _day(entry.get("end_date"), date.min)
    if t.start_date == date.min:
        t.start_date = None
    if t.end_date == date.min:
        t.end_date = None
    session.add(t)
    session.flush()


def ingest(
    session: Session,
    run: IngestRun,
    rows: Sequence[Mapping[str, str]],
    index: Index,
    *,
    commit_every: int | None = None,
) -> Counter[str]:
    """Store the rows as revisioned raw records and normalise them. Idempotent: a second run
    over the same files changes nothing. `commit_every` commits after that many tournaments."""
    counts: Counter[str] = Counter()
    by_tournament: dict[int, list[Mapping[str, str]]] = defaultdict(list)
    entries: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        try:
            played = date.fromisoformat(row.get("date") or "")
        except ValueError:
            played = None
        entry = index.resolve(row.get("tournament") or "", played) if played else None
        if entry is None:
            counts["quarantined:unknown_tournament"] += 1
            session.add(
                IngestIssue(
                    run_id=run.id,
                    kind="unknown_tournament",
                    detail={"tournament": row.get("tournament"), "date": row.get("date")},
                )
            )
            continue
        tid = int(entry["id"])
        entries[tid] = entry
        by_tournament[tid].append(row)

    for n, (tid, group) in enumerate(by_tournament.items(), start=1):
        _tournament(session, run, entries[tid])
        counts["tournaments"] += 1
        keyed: dict[str, list[Mapping[str, str]]] = defaultdict(list)
        for row in group:
            keyed[match_key(tid, row)].append(row)
        for key, same in keyed.items():
            if len({content_hash(dict(r)) for r in same}) > 1:
                counts["quarantined:key_collision"] += len(same)
                session.add(IngestIssue(run_id=run.id, kind="key_collision", detail={"key": key}))
                continue
            counts["duplicate_rows"] += len(same) - 1
            row = dict(same[0])
            outcome = record_payload(session, run, key, row)
            counts[outcome] += 1
            if outcome == "unchanged":
                continue
            record = session.scalars(
                select(RawRecord).filter_by(source_id=run.source_id, source_record_key=key)
            ).one()
            normalized = normalize(row, tid)
            if isinstance(normalized, Rejection):
                existing = session.scalar(select(Match).filter_by(raw_record_id=record.id))
                if existing:
                    session.delete(existing)
                record_issue(
                    session, run, record.id, normalized.kind, {"detail": normalized.detail}
                )
                counts[f"quarantined:{normalized.kind}"] += 1
                continue
            write_match(session, run.source_id, record, normalized)
            counts["normalized"] += 1
            counts[f"status:{normalized.status}"] += 1
        session.flush()
        if commit_every and n % commit_every == 0:
            session.commit()
    return counts


def read(path: Path) -> tuple[list[dict[str, str]], Index]:
    """matches.csv and index.json from a checkout of the dataset."""
    with (path / "matches.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    with (path / "index.json").open(encoding="utf-8") as f:
        index = Index.load(json.load(f))
    return rows, index
