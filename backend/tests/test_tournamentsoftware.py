"""Offline: Tournament Software normalization, record keys, and the committed operation spec."""

import json
from datetime import date
from pathlib import Path

import pytest

from scout.ingest.api_anything import CONSENT_SITES
from scout.ingest.operations import OPERATIONS, TsMatchRow, ts_match_key
from scout.ingest.tournamentsoftware import NormalizedMatch, PlayerRef, Rejection, normalize
from scout.sources import SOURCES

from .ts_fixtures import DOUBLES, ONE_GAME_TO_30, ORG, TOURNAMENT, WALKOVER, row

DAY = date(2026, 1, 5)
SPECS = Path(__file__).resolve().parents[2] / "tools" / "api-anything" / "sites"


def norm(data: dict[str, object]) -> NormalizedMatch:
    result = normalize(TsMatchRow.model_validate(data), DAY)
    assert isinstance(result, NormalizedMatch), result
    return result


def rejected(data: dict[str, object]) -> str:
    result = normalize(TsMatchRow.model_validate(data), DAY)
    assert isinstance(result, Rejection), result
    return result.kind


# --- normalization --------------------------------------------------------------------------


def test_singles_completed_match() -> None:
    m = norm(row())
    assert (m.tournament_key, m.draw_key) == (TOURNAMENT, "7")
    assert (m.discipline, m.round) == ("MS", "Round 1")
    assert (m.status, m.winner_side, m.games) == ("completed", 1, ((21, 15), (21, 18)))
    assert (m.duration_minutes, m.court, m.played_on) == (31, "Main Location - 04", DAY)
    assert m.sides[0] == (PlayerRef(f"member:{ORG}/qa1001", "Alex TESTER"),)


def test_doubles_three_games_and_hour_durations() -> None:
    m = norm(DOUBLES)
    assert m.discipline == "XD"
    assert [len(s) for s in m.sides] == [2, 2]
    assert m.games == ((19, 21), (21, 17), (15, 21))
    assert (m.winner_side, m.duration_minutes) == (2, 65)


def test_walkover_has_winner_and_no_games() -> None:
    m = norm(WALKOVER)
    assert (m.status, m.winner_side, m.games, m.court) == ("walkover", 1, (), "Hall B")


def test_single_game_to_30_is_a_valid_format() -> None:
    # real: Victorian graded events play one game to 30
    m = norm(ONE_GAME_TO_30)
    assert (m.discipline, m.games) == ("WS", ((30, 24),))


def test_retirement_keeps_partial_score() -> None:
    m = norm(row(points=(21, 10, 5, 3), message="Retired"))
    assert (m.status, m.winner_side, m.games) == ("retired", 1, ((21, 10), (5, 3)))


def test_unplayed_match_has_no_winner() -> None:
    m = norm(row(points=(), winner=None))
    assert (m.status, m.winner_side) == ("not_played", None)


@pytest.mark.parametrize(
    ("prefix", "discipline"), [("BS U11", "MS"), ("GS U13", "WS"), ("GD U15", "WD"), ("MX A", "XD")]
)
def test_junior_and_alternate_event_prefixes(prefix: str, discipline: str) -> None:
    doubles = discipline[1] == "D"
    sides = DOUBLES if doubles else row()
    assert norm({**sides, "event": prefix}).discipline == discipline


def test_unknown_event_prefix_leaves_discipline_empty() -> None:
    assert norm(row(event="Open Grade")).discipline is None


def test_player_without_member_id_gets_tournament_scoped_identity() -> None:
    m = norm(row(side1=(("101", "Alex TESTER", None),)))
    assert m.sides[0][0].source_key == f"tplayer:{TOURNAMENT}/101"


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (row(points=(21, 15, 21)), "malformed_score"),
        (row(points=(21, 15)) | {"points": ["21", "x"]}, "malformed_score"),
        (row(side2=(("102", "Sam X", "Q2"), ("103", "Jo Y", "Q3"))), "unexpected_sides"),
        (row() | {"side1Names": list[str]()}, "names_mismatch"),
        (DOUBLES | {"event": "MS A"}, "discipline_mismatch"),
        (row(winner=None), "no_winner"),
        (WALKOVER | {"points": ["21", "0"]}, "walkover_with_score"),
        (row() | {"drawHref": "https://example.test/sport/draw.aspx"}, "missing_identifiers"),
    ],
)
def test_odd_rows_are_rejected_with_a_reason(data: dict[str, object], kind: str) -> None:
    assert rejected(data) == kind


# --- record key -----------------------------------------------------------------------------


def test_key_ignores_side_order_and_outcome() -> None:
    a = TsMatchRow.model_validate(row())
    swapped = TsMatchRow.model_validate(
        row(
            side1=(("102", "Sam EXAMPLE", "QA1002"),),
            side2=(("101", "Alex TESTER", "QA1001"),),
            winner=2,
            points=(15, 21, 18, 21),
        )
    )
    corrected = TsMatchRow.model_validate(row(points=(21, 15, 21, 19)))
    assert ts_match_key(a) == ts_match_key(swapped) == ts_match_key(corrected)
    assert ts_match_key(a) == f"{TOURNAMENT}|7|Round 1|101|102"


def test_key_separates_rounds_and_draws() -> None:
    keys = {
        ts_match_key(TsMatchRow.model_validate(r))
        for r in (row(), row(round_="Round 2"), row(draw=8))
    }
    assert len(keys) == 3


# --- committed operation spec ---------------------------------------------------------------


def test_every_approved_operation_spec_stays_on_authorised_hosts() -> None:
    specs = {p.stem: json.loads(p.read_text()) for p in SPECS.glob("*.json")}
    for name, op in OPERATIONS.items():
        if op.site not in specs:
            continue  # bundled with API Anything (hacker-news), not a reviewed project spec
        spec_op = next(o for o in specs[op.site]["operations"] if o["name"] == op.op)
        assert spec_op["match"]["host"] in SOURCES[op.source_id].hosts, name
        assert spec_op["readOnly"] is True and spec_op["minTier"] == 1, name


def test_committed_specs_hold_no_credentials() -> None:
    for path in SPECS.glob("*.json"):
        text = path.read_text().lower()
        assert "cookie:" not in text and "authorization" not in text, path.name


def test_ts_operations_are_registered_against_the_ba_source() -> None:
    for name in ("tournamentsoftware_ba.match_days", "tournamentsoftware_ba.matches_in_day"):
        assert OPERATIONS[name].source_id == "tournamentsoftware_ba"
    assert SOURCES["tournamentsoftware_ba"].min_interval_s == 5.0


def test_cancelled_match_is_not_played() -> None:
    # real: two "Cancelled" matches, neither row marked as winner
    m = norm(row(points=(), winner=None, message="Cancelled"))
    assert (m.status, m.winner_side) == ("not_played", None)


def test_a_winner_without_a_score_is_a_verified_result() -> None:
    m = norm(row(points=(), winner=2))  # the source marks the winner, publishes no games
    assert (m.status, m.winner_side, m.games) == ("winner_only", 2, ())


def test_dutch_retirement_is_retired() -> None:
    # badvla.tournamentsoftware.com, 2026-11-13: "Opgave" after games were played
    m = norm(row(points=(21, 15, 8, 3), winner=1, message="Opgave"))
    assert (m.status, m.winner_side) == ("retired", 1)


def test_german_cancelled_is_not_played() -> None:
    # dbv.turnier.de, 2026-11-13: "Abgesagt", no games, no winner
    m = norm(row(points=(), winner=None, message="Abgesagt"))
    assert m.status == "not_played" and m.winner_side is None


def test_cancelled_with_a_winner_is_a_walkover() -> None:
    m = norm(row(points=(), winner=1, message="Cancelled"))
    assert (m.status, m.winner_side, m.games) == ("walkover", 1, ())


def test_german_nominal_walkover_score_is_not_kept_as_play() -> None:
    m = norm(row(points=(21, 0, 21, 0), winner=1, message="Abgesagt"))
    assert (m.status, m.winner_side, m.games) == ("walkover", 1, ())


def test_disqualification_keeps_its_winner_and_the_games_played() -> None:
    m = norm(row(points=(21, 15, 4, 2), winner=1, message="Disqualified"))
    assert (m.status, m.winner_side, m.games) == ("disqualified", 1, ((21, 15), (4, 2)))


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (row(points=(), message="Suspended"), "unknown_message"),
        (row(winner=2), "winner_disagrees_with_score"),
    ],
)
def test_unknown_or_contradictory_outcomes_are_rejected(data: dict[str, object], kind: str) -> None:
    assert rejected(data) == kind


def test_spec_requests_and_triggers_stay_on_authorised_hosts() -> None:
    from urllib.parse import urlsplit

    for path in SPECS.glob("*.json"):
        spec = json.loads(path.read_text())
        source_ids = {o.source_id for o in OPERATIONS.values() if o.site == path.stem}
        if path.stem in CONSENT_SITES:
            source_ids.add(CONSENT_SITES[path.stem][0])
        assert source_ids, f"{path.name} maps to no authorised source"
        hosts = {host for sid in source_ids for host in SOURCES[sid].hosts}
        for op in spec["operations"]:
            urls: tuple[str, str] = (op["request"]["url"], op["trigger"]["url"])
            for url in urls:
                assert urlsplit(url).hostname in hosts, (path.name, op["name"], url)


def test_tournament_listing_key_has_its_own_namespace() -> None:
    from scout.ingest.operations import TsTournament, ts_tournament_key

    from .ts_fixtures import listing

    t = TsTournament.model_validate(listing())
    assert ts_tournament_key(t) == f"tournament|{TOURNAMENT}"
    assert not ts_match_key(TsMatchRow.model_validate(row())).startswith("tournament|")


def test_tournament_listing_needs_a_tournament_link() -> None:
    from pydantic import ValidationError

    from scout.ingest.operations import TsTournament

    from .ts_fixtures import listing

    with pytest.raises(ValidationError):
        TsTournament.model_validate(listing() | {"href": "https://ba.tournamentsoftware.com/"})


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (row(side1=(), side2=(), winner=None, points=()), "unfilled_slot"),
        (row(side2=(), winner=None, points=()), "bye"),
        (row(side2=(), points=(21, 10)), "unlinked_player"),
    ],
)
def test_draw_slots_and_byes_are_classified(data: dict[str, object], kind: str) -> None:
    assert rejected(data) == kind


@pytest.mark.parametrize(
    ("event", "discipline"),
    [
        ("Mon U13 Boys Sgls - Group A", "MS"),
        ("Fri U15 Girls Dbls", "WD"),
        ("Tue U17 Mixed Dbls", "XD"),
        ("Open Mens Singles", "MS"),
        ("Mixed Singles", None),
        ("Mon U13 Boys Girls Sgls", None),
        ("Teams", None),
        ("Đơn Nam N3", "MS"),
        ("Đôi Nam Nữ U13 - Group A", "XD"),
        ("Đôi Nữ", "WD"),
        ("Đơn N1", None),  # no gender: unknown
        ("Men\u2019sSingles\u20102 - Group A", "MS"),
        ("MixedDoubles\u20101", "XD"),
    ],
)
def test_discipline_from_event_words(event: str, discipline: str | None) -> None:
    from scout.ingest.tournamentsoftware import discipline_of

    assert discipline_of(event) == discipline


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Casey SYNTHETIC [2]", "Casey SYNTHETIC"),
        ("Ann LEE [3/4]", "Ann LEE"),
        ("Bo  [Bob] KIM", "Bo [Bob] KIM"),
        ("Plain NAME", "Plain NAME"),
    ],
)
def test_seeding_markers_are_not_part_of_a_name(raw: str, clean: str) -> None:
    from scout.ingest.tournamentsoftware import clean_name

    assert clean_name(raw) == clean


def test_seeded_player_keeps_one_identity_and_a_clean_name() -> None:
    m = norm(row(side1=(("101", "Alex TESTER [1]", "QA1001"),)))
    assert m.sides[0][0] == PlayerRef(f"member:{ORG}/qa1001", "Alex TESTER")
