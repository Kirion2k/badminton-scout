"""Fixture providers (ADR-0014): anything that can list upcoming fixtures and their results, in
one normalised shape. A network provider belongs in `scout/ingest/` (the only package that talks
to external sources) and implements the same protocol."""

import csv
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from scout.ingest.provider import ProviderError
from scout.models import FIXTURE_STATUSES

CURATED_SOURCE = "bwf_curated"
FIXTURE_SOURCES = frozenset({CURATED_SOURCE})  # whose players a person links to rated players
CURATED_COLUMNS = (
    "fixture_key", "tournament_key", "tournament_name", "discipline", "round", "scheduled_date",
    "scheduled_start", "timezone", "status", "player_a_bwf_id", "player_a_name",
    "player_b_bwf_id", "player_b_name", "winner", "score", "checked_at", "entered_by",
)  # fmt: skip
_GAMES = re.compile(r"^\d{1,2}-\d{1,2}( \d{1,2}-\d{1,2}){0,2}$")
_WINNER_ALLOWED = {"completed", "retired", "walkover"}
_RESULT = {"completed", "walkover", "retired", "abandoned", "cancelled"}


@dataclass(frozen=True)
class FixtureRow:
    """One fixture as a provider states it now."""

    key: str
    tournament_key: str
    tournament_name: str
    discipline: str
    round: str | None
    scheduled_date: date
    scheduled_start: datetime | None  # timezone-aware, when the provider gives a time
    timezone: str
    status: str
    players: tuple[tuple[str, str], tuple[str, str]]  # (stable player key, display name)
    winner_side: int | None
    score: str | None
    retrieved_at: datetime  # when the provider's data was read
    entered_by: str | None = None  # who typed the result (curated rows), for the four-eyes check

    def payload(self) -> dict[str, Any]:
        """The raw record: JSON-safe and deterministic, so the same state is the same revision.
        When it was read is not part of it, or every re-check would be a new revision."""
        return {
            "key": self.key, "tournament_key": self.tournament_key,
            "tournament_name": self.tournament_name, "discipline": self.discipline,
            "round": self.round, "scheduled_date": self.scheduled_date.isoformat(),
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "timezone": self.timezone, "status": self.status,
            "players": [list(p) for p in self.players], "winner_side": self.winner_side,
            "score": self.score,
        }  # fmt: skip


@dataclass(frozen=True)
class Rejected:
    line: int
    reason: str


class FixtureProvider(Protocol):
    source_id: str
    requests_per_fetch: int  # charged to the source's budget when it has hosts (ADR-0008)

    def fetch(self) -> tuple[list[FixtureRow], list[Rejected]]:
        """Every fixture the provider currently lists. Raises ProviderError when unavailable."""
        ...


def env_credential(name: str) -> str:
    """A provider credential: from the environment only, never code or config files."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ProviderError(f"credential {name} is not set in the environment")
    return value


def parse_row(raw: dict[str, str]) -> FixtureRow:
    """One operator-entered row, strictly: anything doubtful is rejected, never guessed."""
    v = {k: (raw.get(k) or "").strip() for k in CURATED_COLUMNS}
    for required in ("fixture_key", "tournament_key", "tournament_name", "scheduled_date",
                     "timezone", "status", "checked_at"):  # fmt: skip
        if not v[required]:
            raise ValueError(f"{required} is empty")
    if v["discipline"] not in ("MS", "WS"):
        raise ValueError("discipline must be MS or WS")
    if v["status"] not in FIXTURE_STATUSES:
        raise ValueError(f"unknown status {v['status']!r}")
    try:
        zone = ZoneInfo(v["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown timezone {v['timezone']!r}") from None
    day = date.fromisoformat(v["scheduled_date"])
    start = None
    if v["scheduled_start"]:
        local = time.fromisoformat(v["scheduled_start"])
        if local.tzinfo is not None:
            raise ValueError("scheduled_start is the venue's local time, without an offset")
        start = datetime.combine(day, local, zone)
    checked = datetime.fromisoformat(v["checked_at"])
    if checked.tzinfo is None:
        raise ValueError("checked_at needs a UTC offset")
    players: list[tuple[str, str]] = []
    for side in ("a", "b"):
        pid, name = v[f"player_{side}_bwf_id"], v[f"player_{side}_name"]
        if not pid.isdigit():
            # names never identify a player (ADR-0003): a row needs the BWF profile id
            raise ValueError(f"player_{side}_bwf_id must be the BWF profile id")
        players.append((f"bwf-player:{pid}", name or f"BWF player {pid}"))
    if players[0][0] == players[1][0]:
        raise ValueError("the same player on both sides")
    winner = {"": None, "A": 1, "B": 2}.get(v["winner"].upper(), 0)
    if winner == 0:
        raise ValueError("winner must be A, B or empty")
    if winner is not None and v["status"] not in _WINNER_ALLOWED:
        raise ValueError(f"a {v['status']} fixture has no winner")
    if winner is None and v["status"] == "completed":
        raise ValueError("a completed fixture needs a winner")
    if v["status"] in _RESULT and not v["entered_by"]:
        raise ValueError("entered_by (who typed the result) is required with a result")
    if v["score"] and not _GAMES.match(v["score"]):
        raise ValueError("score must be games like 21-15 21-18")
    return FixtureRow(
        key=v["fixture_key"], tournament_key=v["tournament_key"],
        tournament_name=v["tournament_name"], discipline=v["discipline"],
        round=v["round"] or None, scheduled_date=day, scheduled_start=start,
        timezone=v["timezone"], status=v["status"], players=(players[0], players[1]),
        winner_side=winner, score=v["score"] or None, retrieved_at=checked,
        entered_by=v["entered_by"] or None,
    )  # fmt: skip


@dataclass
class CuratedCsv:
    """Fixtures an operator entered by hand from bwfbadminton.com, in a CSV kept outside git."""

    path: Path
    source_id: str = CURATED_SOURCE
    requests_per_fetch: int = 0

    def fetch(self) -> tuple[list[FixtureRow], list[Rejected]]:
        try:
            with self.path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                missing = set(CURATED_COLUMNS) - set(reader.fieldnames or ())
                if missing:
                    raise ProviderError(f"missing columns: {', '.join(sorted(missing))}")
                rows: list[FixtureRow] = []
                rejected: list[Rejected] = []
                for raw in reader:
                    try:
                        rows.append(parse_row(raw))
                    except ValueError as e:
                        rejected.append(Rejected(reader.line_num, str(e)))
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            raise ProviderError(f"unreadable: {e}") from e
        return rows, rejected
