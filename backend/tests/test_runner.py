"""Discovery queue, owner routing and resumable imports, against fake runtimes. No network."""

import http.client
import threading
from collections.abc import Iterator, Mapping
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import MappingProxyType
from typing import Any, ClassVar

import api_anything
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.budget import MemoryBudget
from scout.ingest import runner
from scout.ingest.operations import TsMatchRow, TsTournament
from scout.ingest.provider import ApiAnythingProvider, ProviderError
from scout.ingest.runner import (
    PORTALS,
    CookieWall,
    import_queue,
    record_discovered,
    resolve_owners,
)
from scout.ingest.tournamentsoftware import Rejection, normalize
from scout.models import Match, RawRecord, Tournament, TournamentDiscovery
from scout.sources import SourceRights, Use

from .test_provider import failed, ok
from .ts_fixtures import TOURNAMENT, listing, row

GUID = TOURNAMENT.lower()
BA = PORTALS["ba.tournamentsoftware.com"]


class PortalClient:
    """A fake runtime for one portal: `days` maps YYYYMMDD -> rows ([] means nothing published)."""

    def __init__(
        self,
        days: dict[str, list[dict[str, Any]]] | None = None,
        login: bool = False,
        fail: dict[str, str] | None = None,  # YYYYMMDD -> failure class for that day
    ):
        self.days, self.login, self.fail, self.asked = days or {}, login, fail or {}, list[str]()

    def call(
        self,
        site: str,
        op: str,
        args: Mapping[str, Any] | None = None,
        *,
        max_tier: int | None = None,
    ) -> Mapping[str, Any]:
        args = args or {}
        if self.login:
            return api_anything.Result[Any](failed("auth"))
        if op == "matchDays":
            return api_anything.Result[Any](ok([{"date": d} for d in self.days]))
        self.asked.append(args["date"])
        if args["date"] in self.fail:
            return api_anything.Result[Any](failed(self.fail[args["date"]]))
        rows = self.days.get(args["date"])
        return api_anything.Result[Any](ok(rows) if rows else failed("input"))

    def result(self, result_id: str, offset: int | None = None) -> Mapping[str, Any]:
        raise AssertionError("not cut")


def budget(cap: int | None = None, www_spent: int = 0) -> MemoryBudget:
    rights = SourceRights(frozenset(Use), "test", daily_budget=cap)
    capped = SourceRights(frozenset(Use), "test", daily_budget=10)
    return MemoryBudget(
        MappingProxyType({BA.source_id: rights, "tournamentsoftware": capped}),
        sleep=lambda _: None,
        spent={"tournamentsoftware": www_spent},
    )


def queue(session: Session, *, end: date = date(2026, 1, 6)) -> TournamentDiscovery:
    item = TsTournament.model_validate(listing(dates=(f"{end:%Y-%m-%d} 00:00",)))
    record_discovered(session, BA.source_id, [item], BA.host)
    session.commit()
    found = session.get(TournamentDiscovery, GUID)
    assert found is not None
    return found


def run(
    session: Session, client: PortalClient, cap: int | None = None, *, retry: bool = False
) -> dict[str, int]:
    provider = ApiAnythingProvider(client, sleep=lambda _: None, budget=budget(cap))
    return dict(import_queue(session, provider, max_tournaments=5, retry=retry))


def status(session: Session) -> TournamentDiscovery:
    found = session.get(TournamentDiscovery, GUID)
    assert found is not None
    session.refresh(found)
    return found


pytestmark = pytest.mark.db
DAY1, DAY2, DAY3 = "20260105", "20260106", "20260107"


# --- discovery and routing -------------------------------------------------------------------


def test_discovery_is_deduplicated_across_portals(session: Session) -> None:
    item = TsTournament.model_validate(listing())
    assert record_discovered(session, BA.source_id, [item], BA.host)["new"] == 1
    # the same tournament found again through www search: one row, owner unchanged
    assert record_discovered(session, "tournamentsoftware", [item], None)["seen_again"] == 1
    rows = session.scalars(select(TournamentDiscovery)).all()
    assert len(rows) == 1 and rows[0].owner_source == BA.source_id


@pytest.mark.parametrize(
    ("host", "source", "status"),
    [
        ("ba.tournamentsoftware.com", "tournamentsoftware_ba", "new"),
        ("www.tournamentsoftware.com", "tournamentsoftware", "new"),
        ("bwf.tournamentsoftware.com", "tournamentsoftware_bwf", "login_required"),
        ("bnz.tournamentsoftware.com", "tournamentsoftware_bnz", "new"),
        ("unlisted.tournamentsoftware.com", None, "unauthorised_host"),
    ],
)
def test_owner_routing(session: Session, host: str, source: str | None, status: str) -> None:
    record_discovered(session, "tournamentsoftware", [TsTournament.model_validate(listing())], None)
    counts = resolve_owners(session, lambda guid: host, limit=5)
    row = session.get(TournamentDiscovery, GUID)
    assert row and (row.owner_source, row.status) == (source, status)
    assert counts[f"owner:{host}"] == 1


def test_unfinished_tournaments_are_not_routed_or_imported(session: Session) -> None:
    later = TsTournament.model_validate(listing(dates=("2099-01-01 00:00",)))
    record_discovered(session, "tournamentsoftware", [later], None)
    asked: list[str] = []
    resolve_owners(session, lambda g: asked.append(g) or "www.tournamentsoftware.com", limit=5)
    assert asked == []


# --- resumable import ------------------------------------------------------------------------


def test_complete_import_records_days(session: Session) -> None:
    queue(session)
    counts = run(session, PortalClient({DAY1: [row()], DAY2: [row(draw=8)]}))
    t = session.scalars(select(Tournament).filter_by(source_key=GUID)).one()
    assert (t.name, t.location, t.source_id) == ("Synthetic Open 2026", "Testville", BA.source_id)
    found = session.get(TournamentDiscovery, GUID)
    assert found and found.status == "complete" and found.days_done == [DAY1, DAY2]
    assert counts["normalized"] == 2
    # nothing left to do: a second run asks for nothing
    client = PortalClient({DAY1: [row()], DAY2: [row(draw=8)]})
    run(session, client)
    assert client.asked == []


def test_budget_exhaustion_stops_cleanly_and_resumes(session: Session) -> None:
    queue(session)
    days = {DAY1: [row()], DAY2: [row(draw=8)], DAY3: [row(draw=9)]}
    # matchDays + 1 day fit in 2 requests; the second day does not
    counts = run(session, PortalClient(days), cap=2)
    found = session.get(TournamentDiscovery, GUID)
    assert counts["stopped:budget_exhausted"] == 1
    assert found and found.status == "partial" and found.days_done == [DAY1]
    assert session.scalar(select(func.count()).select_from(Match)) == 1  # day 1 kept
    client = PortalClient(days)
    run(session, client)
    assert client.asked == [DAY2, DAY3]  # day 1 not fetched again
    session.refresh(found)
    assert found.status == "complete"


def test_tournament_with_nothing_published(session: Session) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [], DAY2: [], DAY3: []}))
    found = session.get(TournamentDiscovery, GUID)
    assert found and found.status == "no_matches"
    # not retried by default, so its empty days cost nothing again
    client = PortalClient({DAY1: [row()]})
    run(session, client)
    assert client.asked == []


def test_a_gap_after_matches_is_still_fetched(session: Session) -> None:
    queue(session)
    day4 = "20260108"
    client = PortalClient({DAY1: [row()], DAY2: [], DAY3: [], day4: [row(draw=8)]})
    counts = run(session, client)
    assert client.asked == [DAY1, DAY2, DAY3, day4]  # nothing after the gap is lost
    assert counts["normalized"] == 2 and status(session).status == "complete"


def test_an_empty_last_day_completes_the_tournament(session: Session) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [row()], DAY2: []}))
    assert status(session).status == "complete"  # not partial: no refetch on every run
    client = PortalClient({DAY1: [row()], DAY2: []})
    run(session, client)
    assert client.asked == []


def test_leading_empty_days_stop_early_and_can_be_retried(session: Session) -> None:
    queue(session)
    day4 = "20260108"
    client = PortalClient({DAY1: [], DAY2: [], DAY3: [row()], day4: []})
    run(session, client)
    assert client.asked == [DAY1, DAY2]
    found = status(session)
    assert found.status == "no_matches" and "2 later day(s) not checked" in (found.note or "")
    retry = PortalClient({DAY1: [], DAY2: [], DAY3: [row()], day4: []})
    run(session, retry, retry=True)
    assert retry.asked == [DAY3, day4]  # the checked empty days are not asked again
    assert status(session).status == "complete"


@pytest.mark.parametrize(("klass", "final"), [("auth", "login_required"), ("blocked", "failed")])
def test_walls_on_a_match_day_are_final(session: Session, klass: str, final: str) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [row()], DAY2: [row(draw=8)]}, fail={DAY2: klass}))
    assert status(session).status == final
    client = PortalClient({DAY1: [row()], DAY2: [row(draw=8)]})
    run(session, client)
    assert client.asked == []  # never re-asked automatically (ADR-0008 §3)


def test_failed_tournaments_wait_for_an_explicit_retry(session: Session) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [row()]}, fail={DAY1: "drift"}))
    assert status(session).status == "failed"
    client = PortalClient({DAY1: [row()]})
    run(session, client)
    assert client.asked == []
    run(session, client, retry=True)
    assert client.asked == [DAY1] and status(session).status == "complete"


def test_rows_from_another_portal_store_nothing(session: Session) -> None:
    item = TsTournament.model_validate(listing())
    record_discovered(session, "tournamentsoftware", [item], "www.tournamentsoftware.com")
    session.commit()
    run(session, PortalClient({DAY1: [row()]}))  # www import, ba. draw links
    assert status(session).status == "failed"
    assert session.scalar(select(func.count()).select_from(RawRecord)) == 0
    assert session.scalar(select(func.count()).select_from(Tournament)) == 0


def test_one_source_out_of_budget_does_not_stop_the_other(session: Session) -> None:
    ba_item = TsTournament.model_validate(listing(dates=("2026-01-06 00:00",)))
    www_guid = "dddddddd-0000-0000-0000-000000000000"
    www_item = TsTournament.model_validate(listing(guid=www_guid, dates=("2026-02-01 00:00",)))
    record_discovered(session, BA.source_id, [ba_item], BA.host)
    record_discovered(session, "tournamentsoftware", [www_item], "www.tournamentsoftware.com")
    session.commit()
    client = PortalClient({DAY1: [row()]})
    provider = ApiAnythingProvider(client, sleep=lambda _: None, budget=budget(www_spent=10))
    counts = import_queue(session, provider, max_tournaments=5)  # www (newer) goes first
    assert counts["stopped:budget_exhausted"] == 1
    assert status(session).status == "complete"  # the ba. tournament still ran
    www = session.get(TournamentDiscovery, www_guid)
    assert www and www.status == "partial"


def test_login_wall_is_recorded_not_retried(session: Session) -> None:
    queue(session)
    run(session, PortalClient(login=True))
    found = session.get(TournamentDiscovery, GUID)
    assert found and found.status == "login_required"


def test_unauthorised_owner_is_never_imported(session: Session) -> None:
    record_discovered(session, "tournamentsoftware", [TsTournament.model_validate(listing())], None)
    resolve_owners(session, lambda g: "unlisted.tournamentsoftware.com", limit=5)
    client = PortalClient({DAY1: [row()]})
    run(session, client)
    assert client.asked == []


# --- normalization guards --------------------------------------------------------------------


def test_rows_from_another_host_are_rejected() -> None:
    hosts = frozenset({"www.tournamentsoftware.com"})
    result = normalize(TsMatchRow.model_validate(row()), date(2026, 1, 5), hosts)  # ba. link
    assert isinstance(result, Rejection) and result.kind == "foreign_host"


def test_scores_that_are_not_badminton_are_rejected() -> None:
    result = normalize(TsMatchRow.model_validate(row(points=(6, 4, 6, 3))), date(2026, 1, 5))
    assert isinstance(result, Rejection) and result.kind == "implausible_badminton_score"


# --- owner probe: never follows a redirect ---------------------------------------------------


class _Owner(BaseHTTPRequestHandler):
    location = ""
    cookies: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        _Owner.cookies.append(self.headers.get("Cookie", ""))
        self.send_response(302 if _Owner.location else 200)
        if _Owner.location:
            self.send_header("Location", _Owner.location)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def owner_site(monkeypatch: pytest.MonkeyPatch) -> Iterator[HTTPServer]:
    httpd = HTTPServer(("127.0.0.1", 0), _Owner)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_port

    def connect(host: str, timeout: float = 20) -> http.client.HTTPConnection:
        assert host == "www.tournamentsoftware.com"  # the probe never dials another host
        return http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)

    monkeypatch.setattr(runner.http.client, "HTTPSConnection", connect)
    _Owner.cookies.clear()
    yield httpd
    httpd.shutdown()


@pytest.mark.parametrize(
    ("location", "owner"),
    [
        ("", "www.tournamentsoftware.com"),
        ("https://ba.tournamentsoftware.com/tournament/x", "ba.tournamentsoftware.com"),
        ("https://bnz.tournamentsoftware.com/tournament/x", "bnz.tournamentsoftware.com"),
    ],
)
def test_owner_probe_reads_the_redirect_without_following_it(
    owner_site: HTTPServer, location: str, owner: str
) -> None:
    _Owner.location = location
    probe = runner.www_owner_probe("cp-1-value", MemoryBudget())
    assert probe(GUID) == owner
    assert _Owner.cookies == ["st=cp-1-value"]  # one request, to www only, consent cookie only


@pytest.mark.parametrize(
    ("location", "error"),
    [
        ("/sport/tournament?id=x", ProviderError),  # a www-to-www hop decides nothing
        ("https://www.tournamentsoftware.com/cookiewall/?returnurl=x", CookieWall),
    ],
)
def test_owner_probe_refuses_to_guess(
    owner_site: HTTPServer, location: str, error: type[Exception]
) -> None:
    _Owner.location = location
    with pytest.raises(error):
        runner.www_owner_probe("cp-1-value", MemoryBudget())(GUID)


def test_a_failed_owner_check_marks_that_row_and_goes_on(session: Session) -> None:
    other = "dddddddd-0000-0000-0000-000000000000"
    items = [listing(), listing(guid=other, dates=("2026-01-01 00:00",))]
    record_discovered(
        session, "tournamentsoftware", [TsTournament.model_validate(i) for i in items], None
    )

    def probe(guid: str) -> str:
        if guid == GUID:
            raise ProviderError("HTTP 404")
        return "www.tournamentsoftware.com"

    counts = resolve_owners(session, probe, limit=5)
    assert counts == {"owner:failed": 1, "owner:www.tournamentsoftware.com": 1}
    assert status(session).status == "failed"
    assert resolve_owners(session, probe, limit=5) == {}  # not re-checked every run


def test_tournaments_parked_under_a_newly_authorised_portal_are_queued(session: Session) -> None:
    record_discovered(session, "tournamentsoftware", [TsTournament.model_validate(listing())], None)
    found = session.get(TournamentDiscovery, GUID)
    assert found is not None
    # as recorded before the portal was authorised
    found.owner_host, found.status = "obv.tournamentsoftware.com", "unauthorised_host"
    session.commit()
    assert runner.reroute_parked(session) == 1
    assert (found.owner_source, found.status) == ("tournamentsoftware_obv", "new")


# --- import completeness (what the site tells people about each tournament) --------------------


def state(session: Session) -> tuple[str, int]:
    from scout.api_v1 import _import_states  # pyright: ignore[reportPrivateUsage]

    t = session.scalars(select(Tournament).filter_by(source_key=GUID)).one()
    found = _import_states(session, [t])[t.id]
    return found.status, found.unimported_matches


def test_every_day_imported_is_complete(session: Session) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [row()], DAY2: [row(draw=8)]}))
    assert state(session) == ("complete", 0)


def test_a_rejected_real_match_is_a_gap_not_complete(session: Session) -> None:
    queue(session)
    bye = row(draw=9, side2=(), winner=None, points=())  # a bye is not a match: no gap
    unknown = row(draw=8, points=(), message="Suspended")  # a real match we cannot read
    run(session, PortalClient({DAY1: [row(), bye], DAY2: [unknown]}))
    assert state(session) == ("complete_with_gaps", 1)


def test_days_behind_a_login_make_it_partial(session: Session) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [row()], DAY2: [row(draw=8)]}, fail={DAY2: "auth"}))
    assert state(session) == ("partial", 0)


def test_a_stopped_import_is_partial(session: Session) -> None:
    queue(session)
    run(session, PortalClient({DAY1: [row()], DAY2: [row(draw=8)], DAY3: [row(draw=9)]}), cap=2)
    assert state(session) == ("partial", 0)


def test_a_key_collision_counts_its_lost_matches(session: Session) -> None:
    queue(session)
    twin = row(points=(21, 3, 21, 4))  # same locator as row(), different content
    run(session, PortalClient({DAY1: [row(), twin], DAY2: [row(draw=8)]}))
    assert state(session) == ("complete_with_gaps", 2)


def test_a_corrected_record_is_no_longer_a_gap(session: Session) -> None:
    queue(session)
    unknown = row(draw=8, message="Suspended")  # same locator before and after the correction
    run(session, PortalClient({DAY1: [row()], DAY2: [unknown]}))
    assert state(session) == ("complete_with_gaps", 1)
    found = session.get(TournamentDiscovery, GUID)
    assert found
    found.status, found.days_done = "partial", []  # the scheduled refresh fetches it again
    session.commit()
    run(session, PortalClient({DAY1: [row()], DAY2: [row(draw=8)]}))  # the message is gone
    assert state(session) == ("complete", 0)


def test_a_tournament_still_being_played_is_in_progress(session: Session) -> None:
    from datetime import UTC, datetime, timedelta

    today = datetime.now(UTC).date()
    item = TsTournament.model_validate(
        listing(dates=(f"{today - timedelta(days=1)} 00:00", f"{today + timedelta(days=1)} 23:59"))
    )
    record_discovered(session, BA.source_id, [item], BA.host)
    session.commit()
    from scout.ingest.runner import import_tournament

    found = session.get(TournamentDiscovery, GUID)
    assert found
    yesterday = f"{today - timedelta(days=1):%Y%m%d}"
    client = PortalClient({yesterday: [row()]})
    provider = ApiAnythingProvider(client, sleep=lambda _: None, budget=budget())
    import_tournament(session, provider, BA, found)
    assert state(session)[0] == "in_progress"


def test_tournaments_not_imported_through_the_queue_have_no_state(session: Session) -> None:
    from scout.api_v1 import _import_states  # pyright: ignore[reportPrivateUsage]

    t = Tournament(source_id=BA.source_id, source_key="ffffffff-0000-0000-0000-000000000000")
    session.add(t)
    session.flush()
    assert _import_states(session, [t]) == {}
