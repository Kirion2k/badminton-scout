"""Player API over synthetic data in the test database; junior data must never be served."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import scout.privacy
from scout.db import get_session
from scout.ingest.operations import TsMatchRow
from scout.ingest.tournamentsoftware import ingest_rows
from scout.main import create_app
from scout.models import Event, IngestRun, Player, PlayerLink, SourcePlayer, Tournament

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
    data.flush()
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
