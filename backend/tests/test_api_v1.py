"""Player API over synthetic data in the test database; junior data must never be served."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import scout.privacy
from scout import matchups
from scout.db import get_session
from scout.ingest.operations import TsMatchRow
from scout.ingest.tournamentsoftware import ingest_rows
from scout.main import create_app
from scout.models import (
    Event,
    IngestRun,
    Match,
    Player,
    PlayerLink,
    RatingCurrent,
    RatingModel,
    RatingRun,
    RatingSnapshot,
    SourcePlayer,
    Tournament,
)
from scout.summary import refresh

from .ts_fixtures import DOUBLES, WALKOVER, row

pytestmark = [pytest.mark.db, pytest.mark.anyio]
JUNIOR = row(
    draw=50, event="BS U11", side1=(("501", "Kid ONE", "QJ1"),), side2=(("502", "Kid TWO", "QJ2"),)
)
# a separate tournament holding only a junior event: it must not exist for the API
JUNIOR_GUID = "cccccccc-0000-0000-0000-000000000000"
JUNIOR_ONLY_TOURNAMENT = row(
    draw=60, event="GS U13", side1=(("601", "Kid FOUR", "QJ4"),), side2=(("602", "Kid V", "QJ5"),)
) | {"drawHref": f"https://ba.tournamentsoftware.com/sport/draw.aspx?id={JUNIOR_GUID}&draw=60"}
# an adult who also played a junior event: only the adult match may show
MIXED_AGE = row(draw=51, event="BS U17", side1=(("101", "Alex TESTER", "QA1001"),),
                side2=(("503", "Kid THREE", "QJ3"),))  # fmt: skip


@pytest.fixture(autouse=True)
def restricted_events_hidden(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """These tests prove the hiding path (`event.redistributable`, `_visible_matches`), which is
    what `PUBLISH_RESTRICTED_EVENTS = False` restores. ADR-0010 publishing is tested separately."""
    if "published" not in request.keywords:
        monkeypatch.setattr(scout.privacy, "PUBLISH_RESTRICTED_EVENTS", False)


@pytest.fixture
def data(session: Session) -> Session:
    run = IngestRun(source_id="synthetic")
    session.add(run)
    session.flush()
    rows = [row(), DOUBLES, WALKOVER, JUNIOR, MIXED_AGE, JUNIOR_ONLY_TOURNAMENT]
    items = [TsMatchRow.model_validate(r) for r in rows]
    ingest_rows(session, run, date(2026, 1, 5), items, rows)
    refresh(session, concurrently=False)  # coverage counts, as a sync pass would leave them
    return session


@pytest.fixture
def app(data: Session) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: data
    yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


def player_id(session: Session, name: str) -> int:
    return session.scalars(select(Player.id).filter_by(display_name=name)).one()


async def test_search_tolerates_typos_and_partial_names(api: httpx.AsyncClient) -> None:
    for q in ("Alex Tester", "alex testr", "TESTER"):
        hits = (await api.get("/v1/players", params={"q": q})).json()
        assert hits and hits[0]["name"] == "Alex TESTER", q
    assert hits[0]["matches"] == 2  # the singles and the walkover; not the junior match


async def test_search_never_returns_junior_only_players(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/players", params={"q": "Kid ONE"})).json() == []


async def test_profile_record_counts_adult_matches(api: httpx.AsyncClient, data: Session) -> None:
    body = (await api.get(f"/v1/players/{player_id(data, 'Alex TESTER')}")).json()
    assert body["record"] == {"played": 2, "won": 2, "lost": 0, "walkovers": 1}
    assert body["tournaments"] == 1 and body["disciplines"] == ["MS"]
    assert body["sources"] and body["data_retrieved_at"]


async def test_matches_are_from_the_players_point_of_view(
    api: httpx.AsyncClient, data: Session
) -> None:
    sam = player_id(data, "Sam EXAMPLE")  # side 2, lost 15-21 18-21
    page = (await api.get(f"/v1/players/{sam}/matches")).json()
    singles = next(m for m in page["items"] if m["status"] == "completed")
    assert singles["result"] == "lost"
    assert singles["games"] == [[15, 21], [18, 21]]
    assert [o["name"] for o in singles["opponents"]] == ["Alex TESTER"]
    assert singles["partners"] == [] and singles["source"] and singles["retrieved_at"]


async def test_doubles_lists_partner_and_both_opponents(
    api: httpx.AsyncClient, data: Session
) -> None:
    kim = player_id(data, "Kim SAMPLE")
    m = (await api.get(f"/v1/players/{kim}/matches")).json()["items"][0]
    assert [p["name"] for p in m["partners"]] == ["Lee PLACEHOLDER"]
    assert len(m["opponents"]) == 2 and m["result"] == "lost"


async def test_junior_matches_never_appear(api: httpx.AsyncClient, data: Session) -> None:
    alex = player_id(data, "Alex TESTER")
    page = (await api.get(f"/v1/players/{alex}/matches")).json()
    assert page["total"] == 2
    assert all("U17" not in m["event"] for m in page["items"])
    kid = player_id(data, "Kid ONE")
    assert (await api.get(f"/v1/players/{kid}")).status_code == 404
    assert (await api.get(f"/v1/players/{kid}/matches")).status_code == 404


async def test_tournament_lists_only_adult_events(api: httpx.AsyncClient, data: Session) -> None:
    t = data.scalars(select(Tournament).where(Tournament.source_key != JUNIOR_GUID)).one()
    body = (await api.get(f"/v1/tournaments/{t.id}")).json()
    assert {e["name"] for e in body["events"]} == {"MS C - Group A", "XD Open"}


async def test_merged_player_redirects_after_a_real_merge(
    api: httpx.AsyncClient, data: Session
) -> None:
    from scout import identity
    from scout.models import IdentityCandidate, SourcePlayer

    alex, sam = player_id(data, "Alex TESTER"), player_id(data, "Sam EXAMPLE")
    a, b = sorted(data.scalars(select(SourcePlayer.id).where(
        SourcePlayer.display_name.in_(["Alex TESTER", "Sam EXAMPLE"]))).all())  # fmt: skip
    c = IdentityCandidate(source_player_a_id=a, source_player_b_id=b, rule="test")
    data.add(c)
    data.flush()
    identity.merge(data, c.id, "test", "human:test")
    keep, gone = (alex, sam) if a == data.scalar(select(PlayerLink.source_player_id).where(
        PlayerLink.player_id == alex)) else (sam, alex)  # fmt: skip
    r = await api.get(f"/v1/players/{gone}/matches")
    assert r.status_code == 308 and r.headers["location"] == f"/v1/players/{keep}/matches"
    assert (await api.get(f"/v1/players/{keep}")).status_code == 200


async def test_unknown_ids_are_404(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/players/999999")).status_code == 404
    assert (await api.get("/v1/tournaments/999999")).status_code == 404


async def test_source_identities_are_not_exposed(api: httpx.AsyncClient, data: Session) -> None:
    key = data.scalars(select(SourcePlayer.source_key)).first()
    alex = player_id(data, "Alex TESTER")
    for path in (f"/v1/players/{alex}", f"/v1/players/{alex}/matches"):
        assert key and key not in (await api.get(path)).text  # member ids stay internal


# --- M3 endpoints ---------------------------------------------------------------------------


def junior_only_id(data: Session) -> int:
    return data.scalars(select(Tournament.id).filter_by(source_key=JUNIOR_GUID)).one()


async def test_tournament_list_hides_junior_only_tournaments(
    api: httpx.AsyncClient, data: Session
) -> None:
    page = (await api.get("/v1/tournaments")).json()
    assert page["total"] == 1
    t = page["items"][0]
    assert (t["events"], t["matches"]) == (2, 3)  # MS + XD events; junior events not counted
    assert junior_only_id(data) not in [i["id"] for i in page["items"]]


async def test_tournament_list_search_by_name(api: httpx.AsyncClient, data: Session) -> None:
    t = data.scalars(select(Tournament).where(Tournament.source_key != JUNIOR_GUID)).one()
    t.name = "Synthetic Spring Open"
    data.flush()
    assert (await api.get("/v1/tournaments", params={"q": "spring"})).json()["total"] == 1
    assert (await api.get("/v1/tournaments", params={"q": "winter"})).json()["total"] == 0


async def test_tournament_matches_show_both_sides_and_hide_juniors(
    api: httpx.AsyncClient, data: Session
) -> None:
    t = data.scalars(select(Tournament).where(Tournament.source_key != JUNIOR_GUID)).one()
    page = (await api.get(f"/v1/tournaments/{t.id}/matches")).json()
    assert page["total"] == 3
    assert all("U1" not in m["event"] for m in page["items"])
    completed = [m for m in page["items"] if m["status"] == "completed"]
    singles = next(m for m in completed if m["discipline"] == "MS")
    assert singles["games"] == [[21, 15], [21, 18]] and singles["winner_side"] == 1
    assert [p["name"] for p in singles["side1"]] == ["Alex TESTER"]
    path = f"/v1/tournaments/{t.id}/matches"
    filtered = (await api.get(path, params={"event": "XD Open"})).json()
    assert filtered["total"] == 1
    by_discipline = (await api.get(path, params={"discipline": "MS"})).json()
    assert {m["discipline"] for m in by_discipline["items"]} == {"MS"}
    assert (await api.get(path, params={"discipline": "XX"})).status_code == 422


async def test_junior_only_tournament_is_404_everywhere(
    api: httpx.AsyncClient, data: Session
) -> None:
    tid = junior_only_id(data)
    assert (await api.get(f"/v1/tournaments/{tid}")).status_code == 404
    assert (await api.get(f"/v1/tournaments/{tid}/matches")).status_code == 404


async def test_profile_history_and_opponents(api: httpx.AsyncClient, data: Session) -> None:
    body = (await api.get(f"/v1/players/{player_id(data, 'Alex TESTER')}")).json()
    history = [(t["matches"], t["won"], t["lost"]) for t in body["tournament_history"]]
    assert history == [(2, 2, 0)]
    faced = [(o["name"], o["played"], o["won"]) for o in body["opponents"]]
    assert faced == [("Sam EXAMPLE", 2, 2)]  # the junior opponent of the U17 match is hidden


async def test_match_filters(api: httpx.AsyncClient, data: Session) -> None:
    alex = player_id(data, "Alex TESTER")
    base = f"/v1/players/{alex}/matches"
    assert (await api.get(base, params={"discipline": "MS"})).json()["total"] == 2
    assert (await api.get(base, params={"discipline": "XD"})).json()["total"] == 0
    assert (await api.get(base, params={"result": "lost"})).json()["total"] == 0
    assert (await api.get(base, params={"year": 2026})).json()["total"] == 2
    assert (await api.get(base, params={"year": 2025})).json()["total"] == 0
    assert (await api.get(base, params={"discipline": "XX"})).status_code == 422


async def test_coverage_counts_only_served_data(api: httpx.AsyncClient, data: Session) -> None:
    # move the fixture under a listed provider, so its counts are the ones under test
    data.execute(update(Tournament).values(source_id="tournamentsoftware_ba"))
    refresh(data, concurrently=False)
    body = (await api.get("/v1/coverage")).json()
    ba = next(p for p in body["providers"] if p["source_id"] == "tournamentsoftware_ba")
    # served: MS singles, XD doubles, the walkover. Not the U11, U17 or U13 junior matches
    assert (ba["public_tournaments"], ba["public_matches"], ba["public_players"]) == (1, 3, 6)
    assert "stored_matches" not in ba  # withheld volumes never leave (ADR-0009 §2)
    assert ba["status"] == "connected_importing"
    assert ba["first_played"] == ba["last_played"] == "2026-01-05"
    assert body["excluded"] and body["public_players"] == 6
    assert (body["public_tournaments"], body["public_matches"]) == (1, 3)


async def test_tournament_filters(api: httpx.AsyncClient, data: Session) -> None:
    t = data.scalars(select(Tournament).where(Tournament.source_key != JUNIOR_GUID)).one()
    t.location, t.start_date = "Testville", date(2026, 1, 5)
    data.flush()

    async def total(**params: str | int) -> int:
        return (await api.get("/v1/tournaments", params=params)).json()["total"]

    assert await total(year=2026) == 1 and await total(year=2025) == 0
    assert await total(location="testv") == 1
    assert await total(source="synthetic") == 1 and await total(source="bwf") == 0
    xd = (await api.get("/v1/tournaments", params={"discipline": "XD"})).json()
    assert xd["items"][0]["matches"] == 1  # counts the XD match only
    assert await total(discipline="WD") == 0
    # a discipline played only in a junior event of an adult tournament must not surface it
    junior = data.scalars(select(Event).filter_by(tournament_id=t.id, name="BS U17")).one()
    junior.discipline = "WS"
    data.flush()
    assert await total(discipline="WS") == 0


async def test_coverage_totals_include_sources_without_a_provider_row(
    api: httpx.AsyncClient,
) -> None:
    body = (await api.get("/v1/coverage")).json()  # fixture data stays on `synthetic`
    assert (body["public_tournaments"], body["public_matches"], body["public_players"]) == (1, 3, 6)


@pytest.mark.parametrize(
    ("stored", "runs", "status"),
    [
        (5, ["succeeded"], "connected_importing"),
        (5, ["failed", "failed", "succeeded"], "connected_importing"),  # one bad tournament
        (5, ["failed"] * 3, "source_error"),
        (0, [], "partially_validated"),  # registered operations, nothing imported yet
    ],
)
def test_provider_status_comes_from_results(stored: int, runs: list[str], status: str) -> None:
    from scout.api_v1 import _status  # pyright: ignore[reportPrivateUsage]

    assert _status("tournamentsoftware", stored, runs) == status


def test_providers_without_operations_are_pending() -> None:
    from scout.api_v1 import _status  # pyright: ignore[reportPrivateUsage]

    assert _status("bwf", 0, []) == "pending_access"
    assert _status("tournamentsoftware_bwf", 0, []) == "pending_access"


@pytest.mark.published
async def test_junior_and_para_records_are_served_under_adr_0010(
    api: httpx.AsyncClient, data: Session
) -> None:
    junior = data.scalars(select(Tournament.id).filter_by(source_key=JUNIOR_GUID)).one()
    assert (await api.get(f"/v1/tournaments/{junior}")).status_code == 200
    events = (await api.get("/v1/tournaments", params={"limit": 100})).json()["items"]
    assert junior in {t["id"] for t in events}
    body = (await api.get("/v1/coverage")).json()
    assert body["excluded"] == []  # nothing is withheld any more


async def test_a_withheld_player_is_masked_everywhere(
    api: httpx.AsyncClient, data: Session
) -> None:
    """A removal request: no profile, no search hit, the name masked in others' matches."""
    sam = data.get(Player, player_id(data, "Sam EXAMPLE"))
    assert sam is not None
    sam.withheld_at = datetime.now(UTC)
    data.flush()
    assert (await api.get(f"/v1/players/{sam.id}")).status_code == 404
    hits = (await api.get("/v1/players", params={"q": "Sam EXAMPLE"})).json()
    assert sam.id not in {h["id"] for h in hits}
    t = data.scalars(select(Tournament).where(Tournament.source_key != JUNIOR_GUID)).one()
    body = str((await api.get(f"/v1/tournaments/{t.id}/matches")).json())
    assert "Sam EXAMPLE" not in body and f"'id': {sam.id}," not in body  # not even linkable
    assert "{'id': 0, 'name': 'Name withheld', 'withheld': True}" in body
    alex = (await api.get(f"/v1/players/{player_id(data, 'Alex TESTER')}")).json()
    assert all(o["id"] != sam.id for o in alex["opponents"])
    assert "Sam EXAMPLE" not in str(alex)


async def test_a_merge_cannot_expose_a_withheld_player(
    api: httpx.AsyncClient, data: Session
) -> None:
    from scout.identity import merge
    from scout.models import IdentityCandidate

    alex = data.get(Player, player_id(data, "Alex TESTER"))
    sam = data.get(Player, player_id(data, "Sam EXAMPLE"))
    assert alex and sam
    sam.withheld_at = datetime.now(UTC)
    links = {
        pid: data.scalars(select(PlayerLink.source_player_id).filter_by(player_id=pid)).one()
        for pid in (alex.id, sam.id)
    }
    a, b = sorted([links[alex.id], links[sam.id]])  # the table keeps pairs ordered
    candidate = IdentityCandidate(source_player_a_id=a, source_player_b_id=b, rule="test")
    data.add(candidate)
    data.flush()
    with pytest.raises(ValueError, match="withheld"):
        merge(data, candidate.id, "test", "tester")
    # a withheld record merged earlier: its old URL must not redirect to the visible profile
    sam.merged_into_id = alex.id
    data.flush()
    assert (await api.get(f"/v1/players/{sam.id}")).status_code == 404


async def test_profile_record_by_discipline_counts_decided_matches(
    api: httpx.AsyncClient, data: Session
) -> None:
    body = (await api.get(f"/v1/players/{player_id(data, 'Alex TESTER')}")).json()
    by = {d["discipline"]: (d["won"], d["lost"]) for d in body["by_discipline"]}
    assert sum(w + lo for w, lo in by.values()) == body["record"]["played"]
    assert sum(w for w, _ in by.values()) == body["record"]["won"]


async def test_tournament_list_sorting(api: httpx.AsyncClient) -> None:
    def ids(body: dict[str, list[dict[str, int]]]) -> list[int]:
        return [t["id"] for t in body["items"]]

    newest = ids((await api.get("/v1/tournaments")).json())
    oldest = ids((await api.get("/v1/tournaments", params={"sort": "oldest"})).json())
    assert oldest == list(reversed(newest))
    assert (await api.get("/v1/tournaments", params={"sort": "nope"})).status_code == 422


async def test_a_winner_without_a_score_counts_and_says_so(
    api: httpx.AsyncClient, data: Session
) -> None:
    alex = player_id(data, "Alex TESTER")
    before = (await api.get(f"/v1/players/{alex}")).json()["record"]
    run = IngestRun(source_id="synthetic")
    data.add(run)
    data.flush()
    winner_only = row(draw=40, round_="Final", points=(), winner=1)  # no games, winner marked
    item = TsMatchRow.model_validate(winner_only)
    ingest_rows(data, run, date(2026, 1, 6), [item], [winner_only])
    data.flush()
    after = (await api.get(f"/v1/players/{alex}")).json()["record"]
    assert (after["played"], after["won"]) == (before["played"] + 1, before["won"] + 1)
    history = (await api.get(f"/v1/players/{alex}/matches")).json()["items"]
    final = next(m for m in history if m["round"] == "Final" and m["status"] == "winner_only")
    assert final["games"] == [] and final["result"] == "won"


async def test_event_winner_comes_only_from_a_decided_final(
    api: httpx.AsyncClient, data: Session
) -> None:
    t = data.scalars(select(Tournament).where(Tournament.source_key != JUNIOR_GUID)).one()
    body = (await api.get(f"/v1/tournaments/{t.id}")).json()
    assert all(e["winner"] is None for e in body["events"])  # no round is called a final yet
    # one singles match Alex won becomes that event's final
    singles_ids = select(Event.id).where(Event.tournament_id == t.id, Event.discipline == "MS")
    final_id = data.scalars(
        select(Match.id).where(Match.event_id.in_(singles_ids), Match.winner_side == 1)
    ).first()
    data.execute(update(Match).where(Match.id == final_id).values(round=" Final "))
    data.flush()
    body = (await api.get(f"/v1/tournaments/{t.id}")).json()
    singles = next(e for e in body["events"] if e["discipline"] == "MS")
    assert [p["name"] for p in singles["winner"]] == ["Alex TESTER"]
    # a second "final" in the same event is ambiguous: no winner rather than a guess
    other = data.scalars(
        select(Match.id).where(Match.event_id.in_(singles_ids), Match.id != final_id)
    ).first()
    data.execute(update(Match).where(Match.id == other).values(round="Final"))
    data.flush()
    body = (await api.get(f"/v1/tournaments/{t.id}")).json()
    assert next(e for e in body["events"] if e["discipline"] == "MS")["winner"] is None


async def test_a_file_archive_is_listed_as_an_archive_never_as_connected(
    api: httpx.AsyncClient, data: Session
) -> None:
    def status() -> str:
        return next(p for p in body["providers"] if p["source_id"] == "bwf_historical_compilation")[
            "status"
        ]

    body = (await api.get("/v1/coverage")).json()
    assert status() == "pending_access"  # listed before anything is imported
    data.execute(update(Tournament).values(source_id="bwf_historical_compilation"))
    refresh(data, concurrently=False)
    body = (await api.get("/v1/coverage")).json()
    assert status() == "historical_archive"


async def test_coverage_counts_are_precomputed_and_say_when(
    api: httpx.AsyncClient, data: Session
) -> None:
    body = (await api.get("/v1/coverage")).json()
    assert body["public_matches"] == 3 and body["counts_as_of"] is not None
    m = data.scalars(select(Match)).first()
    assert m is not None
    data.delete(m)
    data.flush()
    assert (await api.get("/v1/coverage")).json()["public_matches"] == 3  # not yet recounted
    refresh(data)  # what the end of every sync pass and data-changing command does
    assert (await api.get("/v1/coverage")).json()["public_matches"] == 2


async def test_head_to_head_counts_meetings_and_wins_from_a_side(
    api: httpx.AsyncClient, data: Session
) -> None:
    alex, sam = player_id(data, "Alex TESTER"), player_id(data, "Sam EXAMPLE")
    h = (await api.get(f"/v1/players/{alex}/head-to-head/{sam}")).json()
    # the singles win and the walkover; the junior match against Alex is never served
    assert (h["meetings"], h["decided"], h["a_won"], h["b_won"], h["walkovers"]) == (2, 2, 2, 0, 1)
    assert all(m["result"] == "won" for m in h["matches"])
    assert h["by_discipline"] == [{"discipline": "MS", "a_won": 2, "b_won": 0}]
    assert h["last_met"] is not None and all(m["source"] for m in h["matches"])
    other_way = (await api.get(f"/v1/players/{sam}/head-to-head/{alex}")).json()
    assert (other_way["a_won"], other_way["b_won"]) == (0, 2)


async def test_head_to_head_needs_opposite_sides(api: httpx.AsyncClient, data: Session) -> None:
    kim, lee = player_id(data, "Kim SAMPLE"), player_id(data, "Lee PLACEHOLDER")
    pat = player_id(data, "Pat DUMMY")
    partners = (await api.get(f"/v1/players/{kim}/head-to-head/{lee}")).json()
    assert partners["meetings"] == 0  # partners are not opponents
    opp = (await api.get(f"/v1/players/{kim}/head-to-head/{pat}")).json()
    assert (opp["meetings"], opp["a_won"], opp["b_won"]) == (1, 0, 1)
    assert opp["matches"][0]["games"] == [[19, 21], [21, 17], [15, 21]]  # Kim's points first


async def test_head_to_head_guards_identity(api: httpx.AsyncClient, data: Session) -> None:
    alex, sam = player_id(data, "Alex TESTER"), player_id(data, "Sam EXAMPLE")
    assert (await api.get(f"/v1/players/{alex}/head-to-head/{alex}")).status_code == 422
    s = data.get(Player, sam)
    assert s is not None
    s.withheld_at = datetime.now(UTC)
    data.flush()
    assert (await api.get(f"/v1/players/{alex}/head-to-head/{sam}")).status_code == 404
    assert (await api.get(f"/v1/players/{sam}/head-to-head/{alex}")).status_code == 404


async def test_head_to_head_follows_merges(api: httpx.AsyncClient, data: Session) -> None:
    kim, pat = player_id(data, "Kim SAMPLE"), player_id(data, "Pat DUMMY")
    lee = data.get(Player, player_id(data, "Lee PLACEHOLDER"))
    assert lee is not None
    lee.merged_into_id = kim  # as if a person had merged them
    data.flush()
    r = await api.get(f"/v1/players/{lee.id}/head-to-head/{pat}")
    assert r.status_code == 308
    assert r.headers["location"] == f"/v1/players/{kim}/head-to-head/{pat}"


async def test_profile_periods_and_formats_add_up(api: httpx.AsyncClient, data: Session) -> None:
    body = (await api.get(f"/v1/players/{player_id(data, 'Alex TESTER')}")).json()
    all_time = next(p for p in body["periods"] if p["since"] is None)
    assert (all_time["won"], all_time["lost"]) == (body["record"]["won"], body["record"]["lost"])
    assert [f["format"] for f in body["by_format"]] == ["singles"]
    assert sum(f["won"] + f["lost"] for f in body["by_format"]) == body["record"]["played"]


def test_period_windows_are_calendar_years() -> None:
    from scout.api_v1 import years_before

    assert years_before(date(2026, 11, 14), 3) == date(2023, 11, 14)
    assert years_before(date(2028, 2, 29), 1) == date(2027, 2, 28)


async def test_two_ids_of_one_person_compare_to_their_profile(
    api: httpx.AsyncClient, data: Session
) -> None:
    kim = player_id(data, "Kim SAMPLE")
    lee = data.get(Player, player_id(data, "Lee PLACEHOLDER"))
    assert lee is not None
    lee.merged_into_id = kim
    data.flush()
    r = await api.get(f"/v1/players/{lee.id}/head-to-head/{kim}")
    assert r.status_code == 308 and r.headers["location"] == f"/v1/players/{kim}"


def serve_ratings(session: Session, players: dict[int, int]) -> int:
    """A served BWF run rating the given players ({player id: matches played})."""
    snap = RatingSnapshot(family="bwf", query_version=2, content_hash="x", counts={})
    model = RatingModel(name="glicko2", config={}, config_hash="cfg")
    session.add_all([snap, model])
    session.flush()
    run = RatingRun(model_id=model.id, snapshot_id=snap.id, pool="bwf", kind="full",
                    code_version="test", metrics={"data_as_of": "2026-07-05"},
                    finished_at=datetime.now(UTC))  # fmt: skip
    session.add(run)
    session.flush()
    for i, (pid, played) in enumerate(players.items()):
        session.add(RatingCurrent(run_id=run.id, pool="bwf:MS", player_id=pid,
                                  rating=1600.0 + 50 * i, rd=70.0, vol=0.06, played=played,
                                  last_played=date(2026, 7, 5), component=0))  # fmt: skip
    session.flush()
    return run.id


async def test_matchup_compares_results_and_never_shows_a_number(
    api: httpx.AsyncClient, data: Session
) -> None:
    alex, sam = player_id(data, "Alex TESTER"), player_id(data, "Sam EXAMPLE")
    r = await api.get("/v1/matchups/compare", params={"a": alex, "b": sam, "discipline": "MS"})
    body = r.json()
    assert r.status_code == 200 and body["outcome"] == "comparison"  # no rating: results only
    assert body["probability_a"] is None and body["a"]["rating"] is None
    assert body["a"]["pool"] == "unrated" and body["reasons"]
    h2h = (await api.get(f"/v1/players/{alex}/head-to-head/{sam}")).json()
    ms = next(d for d in h2h["by_discipline"] if d["discipline"] == "MS")
    assert body["head_to_head"] == [ms["a_won"], ms["b_won"]]
    swapped = (await api.get("/v1/matchups/compare", params={"a": sam, "b": alex})).json()
    assert swapped["head_to_head"] == body["head_to_head"][::-1]
    ws = await api.get("/v1/matchups/compare", params={"a": alex, "b": sam, "discipline": "WS"})
    assert ws.json()["outcome"] == "insufficient_data"


async def test_matchup_identity_rules(api: httpx.AsyncClient, data: Session) -> None:
    kim, pat = player_id(data, "Kim SAMPLE"), player_id(data, "Pat DUMMY")
    assert (await api.get("/v1/matchups/compare", params={"a": kim, "b": kim})).status_code == 422
    lee = data.get(Player, player_id(data, "Lee PLACEHOLDER"))
    assert lee is not None
    lee.merged_into_id = kim
    data.flush()
    r = await api.get("/v1/matchups/compare", params={"a": lee.id, "b": pat, "discipline": "MS"})
    assert r.status_code == 308
    assert r.headers["location"] == f"/v1/matchups/compare?a={kim}&b={pat}&discipline=MS"
    sam = data.get(Player, player_id(data, "Sam EXAMPLE"))
    assert sam is not None
    sam.withheld_at = datetime.now(UTC)
    data.flush()
    assert (
        await api.get("/v1/matchups/compare", params={"a": kim, "b": sam.id})
    ).status_code == 404


async def test_matchup_with_served_ratings_keeps_them_behind_the_flag(
    api: httpx.AsyncClient, data: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    alex, sam = player_id(data, "Alex TESTER"), player_id(data, "Sam EXAMPLE")
    serve_ratings(data, {alex: 40, sam: 40})
    r = await api.get("/v1/matchups/compare", params={"a": alex, "b": sam})
    body = r.json()
    assert body["outcome"] == "comparison" and body["data_as_of"] == "2026-07-05"
    assert body["a"]["pool"] == "bwf:MS" and body["a"]["rating"] is None
    assert "cache-control" not in r.headers
    monkeypatch.setattr(matchups, "PUBLIC_RATINGS", True)
    r = await api.get("/v1/matchups/compare", params={"a": alex, "b": sam})
    assert r.json()["a"]["rating"] == 1600.0 and r.headers["cache-control"] == "no-store"
    monkeypatch.setattr(matchups, "PUBLIC_PROBABILITIES", True)  # still no release evidence
    assert (await api.get("/v1/matchups/compare", params={"a": alex, "b": sam})).json()[
        "probability_a"
    ] is None


async def test_no_route_but_the_gated_matchup_can_carry_a_rating(api: httpx.AsyncClient) -> None:
    """Junior and federation ratings stay private: rating fields exist only in the matchup
    evidence, which is gated by PUBLIC_RATINGS and only ever filled from bwf:* pools."""
    schemas = (await api.get("/openapi.json")).json()["components"]["schemas"]
    words = ("rating", "rd", "volatility", "probability")
    carrying = {
        name for name, schema in schemas.items()
        for prop in schema.get("properties", {})
        if any(w == prop or prop.startswith(f"{w}_") for w in words)
    }  # fmt: skip
    assert carrying == {"Evidence", "Matchup"}


async def test_matchup_never_uses_a_rating_from_before_a_merge(
    api: httpx.AsyncClient, data: Session
) -> None:
    alex, sam = player_id(data, "Alex TESTER"), player_id(data, "Sam EXAMPLE")
    lee = data.get(Player, player_id(data, "Lee PLACEHOLDER"))
    assert lee is not None
    serve_ratings(data, {alex: 40, sam: 40, lee.id: 40})
    before = (await api.get("/v1/matchups/compare", params={"a": alex, "b": sam})).json()
    assert before["outcome"] == "comparison"
    lee.merged_into_id = sam  # identity changed after the ratings were built
    data.flush()
    after = (await api.get("/v1/matchups/compare", params={"a": alex, "b": sam})).json()
    assert after["outcome"] == "identity_uncertain"
