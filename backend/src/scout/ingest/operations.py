"""Approved external operations (ADR-0007). The enforced list: anything not here can't be fetched.

Adding an entry is a reviewed change that needs the operation's evidence in docs/api-anything.md
and a source in scout.sources with the uses the caller will need.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from scout.sources import TS_FEDERATION_PORTALS


@dataclass(frozen=True)
class ApprovedOperation:
    source_id: str  # key into scout.sources.SOURCES
    site: str  # API Anything site
    op: str  # API Anything operation
    model: type[BaseModel]  # one item of the answer's `data` list
    params: frozenset[str]  # argument names a caller may pass
    record_key: Callable[[BaseModel], str]  # stable source record key (ADR-0005), never a score
    attribution: str = ""  # shown wherever the data is displayed
    update_frequency: str = ""
    evidence: str = ""  # validation evidence; details in docs/api-anything.md


class HackerNewsHit(BaseModel):
    """Smoke-test item. Not badminton data, and never stored (source grants LOCAL_RESEARCH only)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    object_id: str = Field(alias="objectID")
    title: str
    url: str | None = None
    points: int | None = None
    num_comments: int | None = None
    author: str
    created_at: datetime


def _hn_key(item: BaseModel) -> str:
    if not isinstance(item, HackerNewsHit):
        raise TypeError(f"expected HackerNewsHit, got {type(item).__name__}")
    return item.object_id


class TsMatchDay(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    date: str = Field(pattern=r"^\d{8}$")


class TsMatchRow(BaseModel):
    """One match as Tournament Software's MatchesInDay fragment shows it.

    Spec: tools/api-anything/sites/tournamentsoftware-ba.json.

    Structure is checked loosely on purpose: an odd row (a bye, a missing side) is rejected by
    normalization as an ingest issue instead of failing the whole day.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    event: str
    draw_href: str = Field(alias="drawHref")
    round: str | None = None
    info: str | None = None
    side1_ids: list[str] = Field(default=[], alias="side1Ids")
    side1_names: list[str] = Field(default=[], alias="side1Names")
    side2_ids: list[str] = Field(default=[], alias="side2Ids")
    side2_names: list[str] = Field(default=[], alias="side2Names")
    row_classes: list[str] = Field(default=[], alias="rowClasses")
    message: str | None = None
    points: list[str] = []
    h2h: str | None = None


def _query(href: str, name: str) -> str:
    found = re.search(rf"[?&]{name}=([^&#]+)", href)
    if not found:
        raise ValueError(f"{name} missing from {href!r}")
    return found.group(1).lower()


def ts_match_key(item: BaseModel) -> str:
    """Tournament + draw + round + both sides' tournament player ids, side order ignored.

    Tournament Software shows no match id. Nothing here is an outcome, so a corrected score is a
    revision of the same record (ADR-0005).
    """
    if not isinstance(item, TsMatchRow):
        raise TypeError(f"expected TsMatchRow, got {type(item).__name__}")
    sides = sorted(",".join(sorted(ids)) for ids in (item.side1_ids, item.side2_ids))
    tournament = _query(item.draw_href, "id")
    return "|".join([tournament, _query(item.draw_href, "draw"), item.round or "", *sides])


class TsTournament(BaseModel):
    """One tournament on the Badminton Australia home tabs (DoTournamentSearch)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    href: str = Field(pattern=r"tournament\?id=[0-9A-Fa-f-]{36}")
    subheading: str | None = None  # "Organiser | City"
    dates: list[str] = []  # start, end ("YYYY-MM-DD HH:MM"); one date for single-day events


def ts_tournament_key(item: BaseModel) -> str:
    if not isinstance(item, TsTournament):
        raise TypeError(f"expected TsTournament, got {type(item).__name__}")
    # own namespace: match keys in the same source start with the bare GUID
    return f"tournament|{_query(item.href, 'id')}"


def _day_key(item: BaseModel) -> str:
    if not isinstance(item, TsMatchDay):
        raise TypeError(f"expected TsMatchDay, got {type(item).__name__}")
    return item.date


# Live checks of the ba. operations on each federation portal (same Tournament Software markup)
_TS_PORTAL_VERIFIED = {
    "bnz": "2026-11-13: tournamentSearch 20/20 listings; one tournament 174/174 rows normalised",
    # after minimal consent (cookie wall); 2026-11-13
    "cbbd": "2026-11-13: one tournament, 3 days, 102/102 rows normalised",
    "dbv": "2026-11-13: one tournament, 2 days, 321/322 rows normalised (1 unknown message)",
    "scotland": "2026-11-13: one tournament imported; 2 others keep match days behind a login",
    "obv": "2026-11-13: reachable after consent; 3 of 3 tournaments show no public match days",
}
_TS_BA_EVIDENCE = (
    "matchesInDay learned 2026-11-12 with `api-anything add` from two distinct tournament/day "
    "inputs, held-out third tournament verified, 438/438 fields equal to an independent parse."
)

_BASE_OPERATIONS: Mapping[str, ApprovedOperation] = MappingProxyType(
    {
        "hacker_news.search": ApprovedOperation(
            source_id="hacker_news_smoke",
            site="hacker-news",
            op="search",
            model=HackerNewsHit,
            params=frozenset({"query", "type", "page"}),
            record_key=_hn_key,
        ),
        "tournamentsoftware_ba.tournament_search": ApprovedOperation(
            source_id="tournamentsoftware_ba",
            site="tournamentsoftware-ba",
            op="tournamentSearch",
            model=TsTournament,
            params=frozenset({"tab", "page"}),
            record_key=ts_tournament_key,
            attribution="Badminton Australia via Tournament Software (ba.tournamentsoftware.com)",
            update_frequency="daily; pages are cumulative (page N lists the first 20*N)",
            evidence="Hand-derived from the home page markup. 4 inputs verified, 20/20 equal to an "
            "independent parse.",
        ),
        "tournamentsoftware_www.find_badminton": ApprovedOperation(
            source_id="tournamentsoftware",
            site="tournamentsoftware-www",
            op="findBadmintonTournaments",
            model=TsTournament,
            params=frozenset({"page", "start", "end"}),
            record_key=ts_tournament_key,
            attribution="Tournament Software (www.tournamentsoftware.com)",
            update_frequency="daily; pages are cumulative (page N lists the first 20*N)",
            evidence="POST /find/tournament/DoSearch, SportID=2 fixed. Pages 1-2 verified at "
            "tier 1 (2026-11-12); SportID 1 and 3 return nothing for the same window.",
        ),
        "tournamentsoftware_www.match_days": ApprovedOperation(
            source_id="tournamentsoftware",
            site="tournamentsoftware-www",
            op="matchDays",
            model=TsMatchDay,
            params=frozenset({"tournament"}),
            record_key=_day_key,
            attribution="Tournament Software (www.tournamentsoftware.com)",
            update_frequency="per tournament",
            evidence="Same markup as ba.; verified on www-owned Gujarat State Championships 2025.",
        ),
        "tournamentsoftware_www.matches_in_day": ApprovedOperation(
            source_id="tournamentsoftware",
            site="tournamentsoftware-www",
            op="matchesInDay",
            model=TsMatchRow,
            params=frozenset({"tournament", "date"}),
            record_key=ts_match_key,
            attribution="Tournament Software (www.tournamentsoftware.com)",
            update_frequency="live during a tournament, corrections possible after",
            evidence="Verified 2026-11-12 on a www-owned tournament: 10/10 rows normalized.",
        ),
        "tournamentsoftware_ba.match_days": ApprovedOperation(
            source_id="tournamentsoftware_ba",
            site="tournamentsoftware-ba",
            op="matchDays",
            model=TsMatchDay,
            params=frozenset({"tournament"}),
            record_key=_day_key,
            attribution="Badminton Australia via Tournament Software (ba.tournamentsoftware.com)",
            update_frequency="per tournament, fixed once scheduled",
            evidence="Hand-derived from the Matches page markup. Held-out tournament verified.",
        ),
        "tournamentsoftware_ba.matches_in_day": ApprovedOperation(
            source_id="tournamentsoftware_ba",
            site="tournamentsoftware-ba",
            op="matchesInDay",
            model=TsMatchRow,
            params=frozenset({"tournament", "date"}),
            record_key=ts_match_key,
            attribution="Badminton Australia via Tournament Software (ba.tournamentsoftware.com)",
            update_frequency="live during a tournament, corrections possible after",
            evidence=_TS_BA_EVIDENCE,
        ),
    }
)


def _federation_ops() -> dict[str, ApprovedOperation]:
    """The ba. operations, on each federation portal in `TS_FEDERATION_PORTALS`."""
    ops: dict[str, ApprovedOperation] = {}
    for key, (host, federation) in TS_FEDERATION_PORTALS.items():
        for name in ("tournament_search", "match_days", "matches_in_day"):
            ops[f"tournamentsoftware_{key}.{name}"] = replace(
                _BASE_OPERATIONS[f"tournamentsoftware_ba.{name}"],
                source_id=f"tournamentsoftware_{key}",
                site=f"tournamentsoftware-{key}",
                attribution=f"{federation} via Tournament Software ({host})",
                evidence="The ba. operation on this portal. Live check: "
                + _TS_PORTAL_VERIFIED.get(key, "not yet run"),
            )
    return ops


OPERATIONS: Mapping[str, ApprovedOperation] = MappingProxyType(
    {**_BASE_OPERATIONS, **_federation_ops()}
)
