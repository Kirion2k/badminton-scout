"""Tournament Software discovery, owner routing and resumable imports (M3.1).

One queue (`tournament_discovery`) for every portal. A tournament is imported from its owning
portal only, under that portal's source, so one seen on several portals is stored once. Imports
commit per match day and record which days are done, so a stopped run resumes where it left off.
"""

import http.client
import re
import urllib.parse
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.budget import Budget, BudgetExhausted
from scout.ingest.event_codes import reclassify
from scout.ingest.operations import TsMatchDay, TsMatchRow, TsTournament
from scout.ingest.provider import ApiAnythingProvider, OperationFailed, ProviderError
from scout.ingest.tournamentsoftware import ingest_rows
from scout.models import Event, IngestRun, Match, Tournament, TournamentDiscovery
from scout.sources import SOURCES, TS_FEDERATION_PORTALS


@dataclass(frozen=True)
class Portal:
    source_id: str
    host: str
    ops: str  # operation-name prefix in scout.ingest.operations
    key: str  # short name on the command line
    site: str  # API Anything site spec (tools/api-anything/sites/<site>.json)


# Portals we may import from. Other hosts need their own recorded authorisation (ADR-0008).
PORTALS = {
    p.host: p
    for p in (
        Portal("tournamentsoftware_ba", "ba.tournamentsoftware.com", "tournamentsoftware_ba",
               "ba", "tournamentsoftware-ba"),
        Portal("tournamentsoftware", "www.tournamentsoftware.com", "tournamentsoftware_www",
               "www", "tournamentsoftware-www"),
        *(
            Portal(f"tournamentsoftware_{key}", host, f"tournamentsoftware_{key}",
                   key, f"tournamentsoftware-{key}")
            for key, (host, _) in TS_FEDERATION_PORTALS.items()
        ),
    )
}  # fmt: skip
# Authorised, but behind a login we have no credentials for (ADR-0008 §7).
LOGIN_HOSTS = {"bwf.tournamentsoftware.com": "tournamentsoftware_bwf"}

# Give up on a tournament after this many empty days before any day with matches.
MAX_EMPTY_DAYS_IN_A_ROW = 2
# Name hints used only to *order* the queue; eligibility is still decided per event (ADR-0009).
_JUNIOR_NAME = re.compile(r"junior|schools?\b|\bu-?1\d\b|u1\d/|under ?1\d", re.IGNORECASE)
_GUID = re.compile(r"id=([0-9A-Fa-f-]{36})")


def _guid(item: TsTournament) -> str:
    found = _GUID.search(item.href)
    if not found:
        raise ValueError(f"no tournament id in {item.href!r}")
    return found.group(1).lower()


def _dates(item: TsTournament) -> tuple[date | None, date | None]:
    days = [date.fromisoformat(d[:10]) for d in item.dates if re.match(r"\d{4}-\d{2}-\d{2}", d)]
    return (days[0], days[-1]) if days else (None, None)


def record_discovered(
    session: Session, via_source: str, items: Sequence[TsTournament], owner_host: str | None
) -> Counter[str]:
    """Upsert discovery rows. `owner_host` is known when a portal lists its own tournaments."""
    counts: Counter[str] = Counter()
    now = datetime.now(UTC)
    for item in items:
        guid = _guid(item)
        row = session.get(TournamentDiscovery, guid)
        organiser, _, location = (item.subheading or "").partition("|")
        start, end = _dates(item)
        if row is None:
            row = TournamentDiscovery(guid=guid, discovered_via=via_source, days_done=[])
            session.add(row)
            counts["new"] += 1
        else:
            counts["seen_again"] += 1
        row.name = " ".join(item.name.split())
        row.organiser, row.location = organiser.strip() or None, location.strip() or None
        row.start_date, row.end_date, row.last_seen_at = start, end, now
        if owner_host and row.owner_host is None:
            _set_owner(row, owner_host)
    session.flush()
    return counts


def _set_owner(row: TournamentDiscovery, host: str) -> None:
    row.owner_host = host
    portal = PORTALS.get(host)
    if portal:
        row.owner_source = portal.source_id
    elif host in LOGIN_HOSTS:
        row.owner_source, row.status = LOGIN_HOSTS[host], "login_required"
        row.note = f"owned by {host}: login required, no credentials"
    else:
        row.owner_source, row.status = None, "unauthorised_host"
        row.note = f"owned by {host}: not in the recorded authorisation (ADR-0008 §2)"


def reroute_parked(session: Session) -> int:
    """Tournaments parked under a portal that has since been authorised go back to the queue."""
    rows = session.scalars(
        select(TournamentDiscovery).where(
            TournamentDiscovery.status == "unauthorised_host",
            TournamentDiscovery.owner_host.in_(list(PORTALS)),
        )
    ).all()
    for row in rows:
        row.status, row.note = "new", None
        row.owner_source = PORTALS[row.owner_host or ""].source_id
    session.commit()
    return len(rows)


Probe = Callable[[str], str]


class CookieWall(ProviderError):
    """www answered with its cookie wall: the stored consent no longer works."""


_WWW = "www.tournamentsoftware.com"


def www_owner_probe(consent_cookie: str, budget: Budget) -> Probe:
    """GET www.tournamentsoftware.com/tournament/{guid} without following redirects: the owner is
    www itself (200) or the redirect target's host. No other host is ever contacted, and only
    the minimal-consent cookie goes to www (ADR-0008, M3.1 amendment)."""

    def probe(guid: str) -> str:
        budget.charge("tournamentsoftware", 1, purpose="owner_check", note=guid)
        conn = http.client.HTTPSConnection(_WWW, timeout=20)
        try:
            conn.request(
                "GET",
                f"/tournament/{urllib.parse.quote(guid)}",
                headers={"User-Agent": "BadmintonScout/0.1 (authorised integration)",
                         "Cookie": f"st={consent_cookie}"},
            )  # fmt: skip
            response = conn.getresponse()
            location = response.getheader("Location") or ""
            response.read()
        except OSError as e:
            raise ProviderError(f"owner check for {guid}: {type(e).__name__}") from e
        finally:
            conn.close()
        if response.status == 200:
            return _WWW
        if response.status in (301, 302, 303, 307, 308) and location:
            if "cookiewall" in location.lower():
                raise CookieWall("owner check met the cookie wall")
            target = urllib.parse.urljoin(f"https://{_WWW}/", location)
            host = urllib.parse.urlsplit(target).hostname
            # a hop that stays on www decides nothing: only a 200 or another host names the owner
            if host and host.lower() != _WWW:
                return host.lower()
        raise ProviderError(f"owner check for {guid}: HTTP {response.status}")

    return probe


def resolve_owners(session: Session, probe: Probe, limit: int) -> Counter[str]:
    """Owner of each started, unrouted tournament, most recent first. A tournament whose check
    fails is marked failed (not re-checked automatically); running out of budget just stops."""
    counts: Counter[str] = Counter()
    today = datetime.now(UTC).date()
    rows = session.scalars(
        select(TournamentDiscovery)
        .where(
            TournamentDiscovery.owner_host.is_(None),
            TournamentDiscovery.status == "new",
            TournamentDiscovery.start_date <= today,  # ongoing ones too: ownership never changes
        )
        .order_by(TournamentDiscovery.end_date.desc())
        .limit(limit)
    ).all()
    for row in rows:
        try:
            _set_owner(row, probe(row.guid))
            counts[f"owner:{row.owner_host}"] += 1
        except BudgetExhausted:
            counts["owners:stopped_budget_exhausted"] += 1
            break
        except CookieWall:
            raise
        except ProviderError as e:
            row.status, row.note = "failed", str(e)[:300]
            counts["owner:failed"] += 1
        session.commit()
    return counts


def import_queue(
    session: Session,
    provider: ApiAnythingProvider,
    *,
    max_tournaments: int,
    sources: set[str] | None = None,
    retry: bool = False,
) -> Counter[str]:
    """Import completed tournaments whose owner we can import from. A source that runs out of
    budget is dropped for this run; the others go on. Failed and empty tournaments are only
    retried with `retry`, so a broken one cannot keep using up the budget (ADR-0008 §3)."""
    today = datetime.now(UTC).date()
    # not_finished here only once it has ended: an ongoing tournament the refresh missed
    statuses = ["new", "partial", "not_finished"] + (["no_matches", "failed"] if retry else [])
    owners = [p.source_id for p in PORTALS.values() if sources is None or p.source_id in sources]
    queue = session.scalars(
        select(TournamentDiscovery).where(
            TournamentDiscovery.status.in_(statuses),
            TournamentDiscovery.owner_source.in_(owners),
            TournamentDiscovery.end_date < today,
        )
    ).all()

    # adult-looking names first, then newest: junior-only tournaments publish nothing (ADR-0009)
    def priority(r: TournamentDiscovery) -> tuple[bool, int]:
        return bool(_JUNIOR_NAME.search(r.name or "")), -(r.end_date or date.min).toordinal()

    totals: Counter[str] = Counter()
    exhausted: set[str] = set()
    started = 0
    for row in sorted(queue, key=priority):
        if started == max_tournaments:
            break
        if row.owner_source in exhausted:
            continue
        portal = next(p for p in PORTALS.values() if p.source_id == row.owner_source)
        started += 1
        counts = import_tournament(session, provider, portal, row)
        totals += counts
        if counts["stopped:budget_exhausted"]:
            exhausted.add(portal.source_id)
    return totals


def import_tournament(
    session: Session,
    provider: ApiAnythingProvider,
    portal: Portal,
    row: TournamentDiscovery,
    *,
    renormalize: bool = False,
) -> Counter[str]:
    """One tournament. Each finished day is committed; a stop or failure keeps those days."""
    counts: Counter[str] = Counter()
    run = IngestRun(source_id=portal.source_id)
    session.add(run)
    row.last_attempt_at = datetime.now(UTC)
    session.commit()
    start_requests = provider.requests_made(portal.source_id)
    try:
        counts += _import_days(session, provider, portal, row, run, renormalize)
        run.status = "succeeded"
    except BudgetExhausted:
        session.rollback()
        # not a source fault: the run did what today's budget allowed (counts say so)
        row.status, run.status = "partial", "succeeded"
        counts["stopped:budget_exhausted"] += 1
    except (ProviderError, ValueError) as e:
        session.rollback()
        row.status, row.note, run.status = "failed", str(e)[:300], "failed"
        counts[f"failed:{type(e).__name__}"] += 1
    except Exception:
        session.rollback()
        row.status, row.note, run.status = "failed", "unexpected error, see logs", "failed"
        run.finished_at = datetime.now(UTC)
        session.commit()
        raise
    # disciplines are read in the tournament's own language, once its events are known
    tournament_id = session.scalar(
        select(Tournament.id).filter_by(source_id=portal.source_id, source_key=row.guid)
    )
    if tournament_id is not None:
        reclassify(session, [tournament_id])
    counts["requests"] += provider.requests_made(portal.source_id) - start_requests
    run.finished_at = datetime.now(UTC)
    run.counts = {"tournament": row.guid, **counts}
    session.commit()
    return counts


def _sync_tournament(session: Session, source_id: str, row: TournamentDiscovery) -> None:
    """The owning source's tournament carries the listing's name, place and dates."""
    t = session.scalar(
        select(Tournament).filter_by(source_id=source_id, source_key=row.guid)
    ) or Tournament(source_id=source_id, source_key=row.guid)
    t.name, t.organiser, t.location = row.name, row.organiser, row.location
    t.start_date, t.end_date = row.start_date, row.end_date
    session.add(t)


def _import_days(
    session: Session,
    provider: ApiAnythingProvider,
    portal: Portal,
    row: TournamentDiscovery,
    run: IngestRun,
    renormalize: bool = False,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    try:
        listed = provider.fetch(f"{portal.ops}.match_days", {"tournament": row.guid}).items
    except OperationFailed as e:
        return _terminal(row, e, counts)
    days = [d.date for d in listed if isinstance(d, TsMatchDay)]
    today = datetime.now(UTC).date()
    done = set(row.days_done or [])  # days fetched: with matches, or checked and empty
    found_matches = _has_matches(session, portal.source_id, row.guid)  # from earlier runs
    empty_in_a_row = 0
    row.status = "partial"
    for day in days:
        if day in done:
            continue
        if not found_matches and empty_in_a_row == MAX_EMPTY_DAYS_IN_A_ROW:
            # leading empty days (mirrored international events): each costs the runtime's
            # re-checks, so stop guessing. Once a day has matches, every later day is fetched.
            counts["days_not_checked"] += 1
            continue
        try:
            result = provider.fetch(
                f"{portal.ops}.matches_in_day", {"tournament": row.guid, "date": day}
            )
        except OperationFailed as e:
            if e.klass != "input":
                return _terminal(row, e, counts)
            empty_in_a_row += 1
            counts["days_without_matches"] += 1
            if _day(day) < today:  # a past day stays empty; today or later may still publish
                done.add(day)
                row.days_done = sorted(done)
                session.commit()
            continue
        empty_in_a_row = 0
        items = [i for i in result.items if isinstance(i, TsMatchRow)]
        foreign = {urllib.parse.urlsplit(i.draw_href).hostname for i in items} - SOURCES[
            portal.source_id
        ].hosts
        if foreign:
            # another portal's rows: store nothing under this source (ADR-0005 provenance)
            raise ProviderError(f"rows link to {sorted(h or '?' for h in foreign)}")
        played_on = _day(day)
        _sync_tournament(session, portal.source_id, row)
        counts += ingest_rows(
            session, run, played_on, items, list(result.rows), renormalize=renormalize
        )
        found_matches = True
        done.add(day)
        row.days_done = sorted(done)
        session.commit()  # this day is safe even if the next one fails
    if not found_matches:
        unchecked = counts["days_not_checked"]
        row.status, row.note = (
            "no_matches",
            "no published matches on its owning portal"
            + (
                f" ({unchecked} later day(s) not checked; --retry-empty checks them)"
                if unchecked
                else ""
            ),
        )
    elif done >= set(days):
        row.status, row.completed_at = "complete", datetime.now(UTC)
    if row.end_date is None or row.end_date >= today:
        row.status = "not_finished"  # still being played: the scheduled refresh comes back
    counts["days"] += len(done)
    return counts


def _day(day: str) -> date:
    return datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC).date()


def discover(
    session: Session,
    provider: ApiAnythingProvider,
    portal: Portal,
    *,
    pages: int,
    window: tuple[date, date] | None = None,
) -> Counter[str]:
    """One listing request (pages are cumulative: page N returns the first 20*N). www searches
    `window` (default: the last 30 days and the next 14); a national portal searches `window`
    with its own date search, else lists its recent tournaments."""
    if portal.source_id != "tournamentsoftware":
        if window:
            start, end = window
            found = provider.fetch(
                f"{portal.ops}.find_tournaments",
                {"page": pages, "start": f"{start:%Y-%m-%d}T00:00", "end": f"{end:%Y-%m-%d}T00:00"},
            )
        else:
            found = provider.fetch(
                f"{portal.ops}.tournament_search", {"tab": "Recent", "page": pages}
            )
        owner: str | None = portal.host  # a national portal lists its own tournaments
    else:
        today = datetime.now(UTC).date()
        start, end = window or (today - timedelta(days=30), today + timedelta(days=14))
        found = provider.fetch(
            f"{portal.ops}.find_badminton",
            {"page": pages, "start": f"{start:%Y-%m-%d}T00:00", "end": f"{end:%Y-%m-%d}T00:00"},
        )
        owner = None  # resolved per tournament (www_owner_probe)
    items = [i for i in found.items if isinstance(i, TsTournament)]
    counts = record_discovered(session, portal.source_id, items, owner)
    counts["listed"] += len(items)
    session.commit()
    return counts


def _has_matches(session: Session, source_id: str, guid: str) -> bool:
    return (
        session.scalar(
            select(Match.id)
            .join(Event, Event.id == Match.event_id)
            .join(Tournament, Tournament.id == Event.tournament_id)
            .where(Tournament.source_id == source_id, Tournament.source_key == guid)
            .limit(1)
        )
        is not None
    )


def _terminal(row: TournamentDiscovery, e: OperationFailed, counts: Counter[str]) -> Counter[str]:
    """Login walls and blocks are final: never re-asked automatically (ADR-0008 §3)."""
    if e.klass == "auth":
        row.status, row.note = "login_required", "the tournament's pages need a login"
    elif e.klass == "blocked":
        row.status, row.note = "failed", "blocked by the provider; not retried automatically"
    else:
        raise e
    counts[f"stopped:{e.klass}"] += 1
    return counts


def discovery_counts(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(TournamentDiscovery.owner_source, TournamentDiscovery.status)
    ).all()
    return dict(Counter(f"{s or 'unrouted'}:{st}" for s, st in rows))
