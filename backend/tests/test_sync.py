"""Scheduled sync (`scout sync`), against a fake runtime and synthetic tournaments. No network."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import Any

import api_anything
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

import scout.privacy
from scout.api_v1 import coverage
from scout.budget import MemoryBudget
from scout.ingest import sync as sync_module
from scout.ingest.provider import ApiAnythingProvider
from scout.ingest.runner import PORTALS, CookieWall
from scout.ingest.runner import Portal as PortalSpec
from scout.ingest.sync import has_history_search, provider_lock, refresh_due, sync_provider
from scout.models import Event, Game, RawRecordRevision, SyncRun, TournamentDiscovery
from scout.sources import SourceRights, Use

from .test_provider import failed, ok
from .ts_fixtures import TOURNAMENT, listing, row

pytestmark = pytest.mark.db
BA = PORTALS["ba.tournamentsoftware.com"]
WWW = PORTALS["www.tournamentsoftware.com"]
GUID = TOURNAMENT.lower()
OTHER = "dddddddd-0000-0000-0000-000000000000"
TODAY = datetime.now(UTC).date()
PAST = date(2026, 1, 5)  # long finished: queue work, never refreshed


@pytest.fixture(autouse=True)
def no_portal_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Portal history search off unless a test turns it on: the other tests count exact calls."""

    def www_only(p: PortalSpec) -> bool:
        return p.source_id == "tournamentsoftware"

    monkeypatch.setattr(sync_module, "has_history_search", www_only)


def ymd(d: date) -> str:
    return f"{d:%Y%m%d}"


def at(r: dict[str, Any], guid: str) -> dict[str, Any]:
    return r | {"drawHref": r["drawHref"].replace(TOURNAMENT, guid)}


def entry(guid: str, start: date, end: date) -> dict[str, Any]:
    return listing(guid=guid.upper(), dates=(f"{start} 00:00", f"{end} 23:59"))


class Portal:
    """A fake BA portal: a listing, and days of rows per tournament ([] = nothing published)."""

    def __init__(self) -> None:
        self.listing: list[dict[str, Any]] = []
        self.days: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.fail: dict[tuple[str, str], str] = {}  # (guid, day) -> failure class
        self.calls: list[str] = []
        self.search_fails = False
        self.searches: list[tuple[str, str]] = []  # www search windows asked for
        self.empty_is_input = False  # answer an empty search as the real runtime does

    def call(
        self,
        site: str,
        op: str,
        args: Mapping[str, Any] | None = None,
        *,
        max_tier: int | None = None,
    ) -> Mapping[str, Any]:
        args = args or {}
        self.calls.append(op)
        if op in ("findBadmintonTournaments", "findTournaments"):
            self.searches.append((args["start"][:10], args["end"][:10]))
            lo, hi = args["start"][:10], args["end"][:10]
            hits = [i for i in self.listing if lo <= i["dates"][0][:10] <= hi]
            if not hits and self.empty_is_input:
                return api_anything.Result[Any](failed("input", reason="no results for these args"))
            return api_anything.Result[Any](ok(hits[: 20 * int(args["page"])]))
        if op == "tournamentSearch":
            answer = failed("drift") if self.search_fails else ok(self.listing)
            return api_anything.Result[Any](answer)
        days = self.days[args["tournament"].lower()]
        if op == "matchDays":
            return api_anything.Result[Any](ok([{"date": d} for d in days]))
        key = (args["tournament"].lower(), args["date"])
        if key in self.fail:
            return api_anything.Result[Any](failed(self.fail[key]))
        rows = days.get(args["date"])
        return api_anything.Result[Any](ok(rows) if rows else failed("input"))

    def result(self, result_id: str, offset: int | None = None) -> Mapping[str, Any]:
        raise AssertionError("not cut")


def sync(
    engine: Engine,
    session: Session,
    portal: Portal,
    *,
    cap: int | None = None,
    on: Any = BA,
    **kw: Any,
) -> SyncRun:
    rights = SourceRights(frozenset(Use), "test", daily_budget=cap)
    budget = MemoryBudget(
        MappingProxyType({BA.source_id: rights, WWW.source_id: rights}), sleep=lambda _: None
    )
    provider = ApiAnythingProvider(portal, sleep=lambda _: None, budget=budget)
    return sync_provider(engine, session, provider, on, **kw)


def queued(session: Session, guid: str = GUID) -> TournamentDiscovery:
    found = session.get(TournamentDiscovery, guid)
    assert found is not None
    session.refresh(found)
    return found


def finished_portal() -> Portal:
    portal = Portal()
    portal.listing = [entry(GUID, PAST, PAST + timedelta(days=1))]
    portal.days[GUID] = {ymd(PAST): [row()], ymd(PAST + timedelta(days=1)): [row(draw=8)]}
    return portal


# --- a scheduled pass --------------------------------------------------------------------------


def test_a_pass_discovers_and_imports_new_tournaments(engine: Engine, session: Session) -> None:
    portal = finished_portal()
    planned = datetime.now(UTC) + timedelta(hours=24)
    run = sync(engine, session, portal, next_run_at=planned)
    assert (run.status, run.discovered, run.next_run_at) == ("succeeded", True, planned)
    assert run.counts["discovery:new"] == 1 and run.counts["normalized"] == 2
    assert queued(session).status == "complete"


def test_a_second_pass_costs_nothing_for_settled_work(engine: Engine, session: Session) -> None:
    portal = finished_portal()
    sync(engine, session, portal)
    revisions = session.scalar(select(func.count()).select_from(RawRecordRevision))
    portal.calls.clear()
    run = sync(engine, session, portal)
    assert portal.calls == []  # discovery is daily; a finished, imported tournament is settled
    assert run.status == "succeeded" and not run.discovered
    assert session.scalar(select(func.count()).select_from(RawRecordRevision)) == revisions


def test_budget_exhaustion_is_incomplete_and_the_next_pass_resumes(
    engine: Engine, session: Session
) -> None:
    portal = finished_portal()
    third = PAST + timedelta(days=2)
    portal.listing = [entry(GUID, PAST, third)]
    portal.days[GUID][ymd(third)] = [row(draw=9)]
    run = sync(engine, session, portal, cap=3)  # search + match days + one day
    assert run.status == "incomplete" and run.counts["stopped:budget_exhausted"] == 1
    assert queued(session).days_done == [ymd(PAST)]
    portal.calls.clear()
    run = sync(engine, session, portal)
    assert run.status == "succeeded" and queued(session).status == "complete"
    assert portal.calls == ["matchDays", "matchesInDay", "matchesInDay"]  # day 1 not again


def test_a_second_worker_on_the_same_provider_is_skipped(engine: Engine, session: Session) -> None:
    portal = finished_portal()
    with provider_lock(engine, BA.source_id) as held:
        assert held
        run = sync(engine, session, portal)
    assert run.status == "skipped" and portal.calls == []
    assert sync(engine, session, portal).status == "succeeded"  # free again


def test_an_interrupted_pass_is_closed_by_the_next(engine: Engine, session: Session) -> None:
    dead = SyncRun(source_id=BA.source_id)
    session.add(dead)
    session.commit()
    sync(engine, session, finished_portal())
    session.refresh(dead)
    assert (dead.status, dead.note) == ("failed", "interrupted")


def test_one_failing_tournament_does_not_stop_the_pass(engine: Engine, session: Session) -> None:
    portal = finished_portal()
    portal.listing.append(entry(OTHER, PAST, PAST))
    portal.days[OTHER] = {ymd(PAST): [at(row(), OTHER)]}
    portal.fail[(GUID, ymd(PAST))] = "drift"
    run = sync(engine, session, portal)
    assert run.status == "succeeded" and run.counts["failed:OperationFailed"] == 1
    assert queued(session).status == "failed" and queued(session, OTHER).status == "complete"


# --- refresh: ongoing and recently finished ----------------------------------------------------


def test_an_ongoing_tournament_stays_open_and_is_refreshed(
    engine: Engine, session: Session
) -> None:
    yesterday = TODAY - timedelta(days=1)
    portal = Portal()
    portal.listing = [entry(GUID, yesterday, TODAY + timedelta(days=1))]
    portal.days[GUID] = {ymd(yesterday): [row()], ymd(TODAY): []}
    sync(engine, session, portal)
    found = queued(session)
    assert found.status == "not_finished"
    assert found.days_done == [ymd(yesterday)]  # today's empty day may still publish
    assert refresh_due(session, BA.source_id, datetime.now(UTC) + timedelta(hours=21))


def test_a_correction_is_picked_up_by_the_refresh(engine: Engine, session: Session) -> None:
    yesterday = TODAY - timedelta(days=1)
    portal = Portal()
    portal.listing = [entry(GUID, yesterday, yesterday)]
    portal.days[GUID] = {ymd(yesterday): [row(points=(21, 15, 21, 18))]}
    sync(engine, session, portal)
    found = queued(session)
    assert found.status == "complete"
    found.last_attempt_at = datetime.now(UTC) - timedelta(hours=21)  # a day later
    session.commit()
    portal.days[GUID][ymd(yesterday)] = [row(points=(21, 15, 18, 21, 21, 10))]  # corrected
    run = sync(engine, session, portal)
    assert run.counts["refreshed"] == 1 and run.counts["refresh:revised"] == 1
    assert session.scalar(select(func.count()).select_from(Game)) == 3
    assert session.scalar(select(func.count()).select_from(RawRecordRevision)) == 2


def test_settled_tournaments_are_never_refreshed(session: Session) -> None:
    item = entry(GUID, TODAY - timedelta(days=10), TODAY - timedelta(days=10))
    portal = Portal()
    portal.listing = [item]
    from scout.ingest.operations import TsTournament
    from scout.ingest.runner import record_discovered

    record_discovered(session, BA.source_id, [TsTournament.model_validate(item)], BA.host)
    found = queued(session)
    found.status, found.last_attempt_at = "complete", datetime.now(UTC) - timedelta(days=5)
    assert refresh_due(session, BA.source_id, datetime.now(UTC)) == []  # fetched 5 days after end
    found.last_attempt_at = datetime.now(UTC) - timedelta(days=9)  # fetched the day it ended
    assert refresh_due(session, BA.source_id, datetime.now(UTC)) == [found]


# --- privacy and freshness reporting -----------------------------------------------------------


def test_synced_junior_events_stay_private_and_freshness_is_reported(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scout.privacy, "PUBLISH_RESTRICTED_EVENTS", False)  # the hiding path
    portal = finished_portal()
    portal.days[GUID][ymd(PAST)].append(row(draw=20, event="BS U15"))
    portal.listing.append(entry(OTHER, TODAY + timedelta(days=5), TODAY + timedelta(days=6)))
    planned = datetime.now(UTC) + timedelta(hours=24)
    sync(engine, session, portal, next_run_at=planned)
    junior = session.scalars(select(Event).filter_by(name="BS U15")).one()
    assert not junior.redistributable
    body = coverage(session)
    ba = next(p for p in body.providers if p.source_id == BA.source_id)
    assert (ba.public_matches, ba.public_tournaments) == (2, 1)  # the U15 match is not counted
    assert ba.last_sync_status == "succeeded" and ba.last_sync_at is not None
    assert body.next_sync_at == planned and body.last_sync_at is not None
    assert ba.awaiting_import == 1 and body.awaiting_import == 1  # the upcoming tournament


def test_no_schedule_means_no_next_sync(engine: Engine, session: Session) -> None:
    sync(engine, session, finished_portal())
    assert coverage(session).next_sync_at is None


# --- failures the scheduler must survive -------------------------------------------------------


def test_a_failed_search_still_works_the_queue_and_is_not_repeated(
    engine: Engine, session: Session
) -> None:
    portal = finished_portal()
    sync(engine, session, portal)  # queue a tournament, then make it look unimported
    found = queued(session)
    found.status, found.days_done = "new", []
    session.query(SyncRun).delete()
    session.commit()
    portal.search_fails = True
    portal.calls.clear()
    run = sync(engine, session, portal)
    assert run.status == "succeeded" and run.counts["discovery:failed:OperationFailed"] == 1
    assert queued(session).status == "complete"  # the queue still moved
    portal.calls.clear()
    sync(engine, session, portal)
    assert "tournamentSearch" not in portal.calls  # the failed search counts as today's


def test_a_cookie_wall_is_recorded_and_handed_to_the_caller(
    engine: Engine, session: Session
) -> None:
    def wall(guid: str) -> str:
        raise CookieWall("cookie wall")

    from scout.ingest.operations import TsTournament
    from scout.ingest.runner import record_discovered

    unrouted = TsTournament.model_validate(entry(OTHER, PAST, PAST))
    record_discovered(session, "tournamentsoftware", [unrouted], None)  # owner not yet checked
    session.commit()
    portal = finished_portal()
    with pytest.raises(CookieWall):  # so `scout sync` renews consent
        sync(engine, session, portal, probe=wall)
    run = session.scalars(select(SyncRun)).one()
    assert run.status == "failed" and "cookie wall" in (run.note or "")
    assert sync(engine, session, portal).status == "succeeded"  # the lock was released


def test_an_ongoing_tournament_the_refresh_missed_is_finished_by_the_queue(
    engine: Engine, session: Session
) -> None:
    portal = finished_portal()
    sync(engine, session, portal)
    found = queued(session)
    found.status, found.days_done = "not_finished", [ymd(PAST)]  # last seen while being played
    session.commit()
    portal.calls.clear()
    sync(engine, session, portal)
    assert queued(session).status == "complete"
    assert portal.calls == ["matchDays", "matchesInDay"]  # only the missing day


def test_refreshes_leave_room_for_the_queue(engine: Engine, session: Session) -> None:
    yesterday = TODAY - timedelta(days=1)
    portal = Portal()
    guids = [f"eeeeeeee-0000-0000-0000-00000000000{i}" for i in range(4)]
    for g in guids:
        portal.listing.append(entry(g, yesterday, yesterday))
        portal.days[g] = {ymd(yesterday): [at(row(), g)]}
    sync(engine, session, portal, max_tournaments=4)  # imports all four (queue: they ended)
    for g in guids:
        queued(session, g).last_attempt_at = datetime.now(UTC) - timedelta(hours=21)
    portal.listing.append(entry(GUID, PAST, PAST))
    portal.days[GUID] = {ymd(PAST): [row()]}
    session.query(SyncRun).delete()
    session.commit()
    run = sync(engine, session, portal, max_tournaments=4)
    assert run.counts["refreshed"] == 2  # half the slots
    assert queued(session).status == "complete"  # the new tournament still got imported


# --- history backfill (www search) -------------------------------------------------------------


def listed_on(guid: str, day: date) -> dict[str, Any]:
    return entry(guid, day, day)


def test_backfill_walks_back_and_the_next_pass_resumes(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "BACKFILL_SEARCHES", 2)
    portal = Portal()
    portal.listing = [listed_on(GUID, TODAY - timedelta(days=40)),
                      listed_on(OTHER, TODAY - timedelta(days=50))]  # fmt: skip
    run = sync(engine, session, portal, on=WWW)
    assert run.backfilled_to == TODAY - timedelta(days=44)  # two weeks back from today-30
    assert session.get(TournamentDiscovery, GUID) is not None
    assert session.get(TournamentDiscovery, OTHER) is None  # not reached yet
    portal.searches.clear()
    sync(engine, session, portal, on=WWW)
    assert portal.searches[0] == (f"{TODAY - timedelta(days=51)}", f"{TODAY - timedelta(days=44)}")
    assert session.get(TournamentDiscovery, OTHER) is not None


def test_a_full_search_is_split_so_nothing_is_cut_off(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "BACKFILL_SEARCHES", 1)
    monkeypatch.setattr(sync_module, "BACKFILL_PAGES", 1)  # 20 listings per search
    day = TODAY - timedelta(days=33)
    portal = Portal()
    portal.listing = [listed_on(f"ffffffff-0000-0000-0000-{i:012d}", day + timedelta(days=i % 3))
                      for i in range(25)]  # fmt: skip
    run = sync(engine, session, portal, on=WWW)
    assert run.counts["backfill:searches"] > 1
    found = session.scalar(select(func.count()).select_from(TournamentDiscovery))
    assert found == 25


def test_backfill_stops_at_the_floor(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "BACKFILL_FLOOR", TODAY - timedelta(days=40))
    portal = Portal()
    run = sync(engine, session, portal, on=WWW)
    assert run.counts["backfill:reached_floor"] == 1
    assert run.backfilled_to == TODAY - timedelta(days=40)
    portal.searches.clear()
    run = sync(engine, session, portal, on=WWW)
    assert portal.searches == []  # nothing left to search, and discovery already ran today


def test_owners_are_checked_before_searching_further_back(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scout.ingest.operations import TsTournament
    from scout.ingest.runner import record_discovered

    monkeypatch.setattr(sync_module, "BACKFILL_SEARCHES", 1)
    unrouted = TsTournament.model_validate(entry(OTHER, PAST, PAST))
    record_discovered(session, "tournamentsoftware", [unrouted], None)  # the backlog
    session.commit()
    portal = Portal()

    def probe(guid: str) -> str:
        portal.calls.append("ownerCheck")
        return "www.tournamentsoftware.com"

    portal.days[OTHER] = {}
    sync(engine, session, portal, on=WWW, probe=probe)
    searches = [i for i, c in enumerate(portal.calls) if c == "findBadmintonTournaments"]
    # daily discovery, then the owner check, then the history search
    assert portal.calls.index("ownerCheck") < searches[-1]
    assert len(searches) == 2


def test_a_portal_with_its_own_date_search_backfills_its_history(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "has_history_search", has_history_search)
    monkeypatch.setattr(sync_module, "BACKFILL_SEARCHES", 2)
    old = TODAY - timedelta(days=70)
    portal = Portal()
    portal.listing = [listed_on(OTHER, old)]  # beyond the recent tab, reachable only by date
    portal.days[OTHER] = {ymd(old): [at(row(), OTHER)]}
    run = sync(engine, session, portal, on=BA)
    assert run.backfilled_to == TODAY - timedelta(days=30 + 2 * 28)  # four-week windows
    found = queued(session, OTHER)
    assert found.owner_host == BA.host  # a portal's own search lists its own tournaments
    assert "findTournaments" in portal.calls


def test_a_portal_without_an_approved_date_search_does_not_backfill(
    engine: Engine, session: Session
) -> None:
    from scout.ingest.runner import PORTALS

    obv = next(p for p in PORTALS.values() if p.key == "obv")
    assert not has_history_search(obv)
    assert has_history_search(BA)


def test_a_portal_reads_page_one_and_splits_a_full_window(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "has_history_search", has_history_search)
    monkeypatch.setattr(sync_module, "BACKFILL_SEARCHES", 1)
    day = TODAY - timedelta(days=40)
    portal = Portal()
    guids = [f"abababab-0000-0000-0000-{i:012d}" for i in range(25)]
    portal.listing = [listed_on(g, day + timedelta(days=i % 9)) for i, g in enumerate(guids)]
    portal.days = {g: {} for g in guids}  # listed only; nothing to import
    run = sync(engine, session, portal, on=BA)
    assert run.counts["backfill:searches"] > 1  # 20 on page one: the window was split
    assert session.scalar(select(func.count()).select_from(TournamentDiscovery)) == 25


def test_an_empty_window_does_not_stop_the_history_search(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "has_history_search", has_history_search)
    monkeypatch.setattr(sync_module, "BACKFILL_SEARCHES", 3)
    old = TODAY - timedelta(days=30 + 2 * 28 + 5)  # only the third window has a tournament
    portal = Portal()
    portal.listing = [listed_on(OTHER, old)]
    portal.days[OTHER] = {}
    portal.empty_is_input = True  # the runtime's answer to a search with no results
    run = sync(engine, session, portal, on=BA)
    assert (
        run.counts["backfill:searches"] == 3 and "backfill:failed:OperationFailed" not in run.counts
    )
    assert session.get(TournamentDiscovery, OTHER) is not None
