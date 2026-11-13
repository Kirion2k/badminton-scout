"""Automatic identity resolution on synthetic tournaments (invented names and ids). No network."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import identity, identity_auto
from scout.identity import generate_candidates
from scout.ingest.operations import TsMatchRow
from scout.ingest.tournamentsoftware import ingest_rows
from scout.models import IdentityCandidate, IngestRun, Player, PlayerLink, SourcePlayer

from .ts_fixtures import TOURNAMENT, row

pytestmark = pytest.mark.db
DAY = date(2026, 1, 5)
BA = "tournamentsoftware_ba"
T1, T2, T3 = (f"{n}aaaaaaa-1111-2222-3333-444444444444" for n in "123")


def play(
    session: Session, tournament: str, rows: list[dict[str, Any]], source: str = "synthetic"
) -> None:
    run = IngestRun(source_id=source)
    session.add(run)
    session.flush()
    rows = [r | {"drawHref": r["drawHref"].replace(TOURNAMENT, tournament)} for r in rows]
    ingest_rows(session, run, DAY, [TsMatchRow.model_validate(r) for r in rows], rows)
    session.flush()


def doubles(draw: int, a: tuple[Any, Any], b: tuple[Any, Any]) -> dict[str, Any]:
    return row(draw=draw, event="MD A", side1=a, side2=b, points=(21, 10, 21, 12))


# five members of one issuer make a tournament clearly that issuer's (the Tier B precondition)
CLUB = [(str(200 + i), f"Member{i} CLUB", f"QA20{i}") for i in range(4)]


def player_of(session: Session, name: str) -> set[int]:
    return set(
        session.scalars(
            select(PlayerLink.player_id)
            .join(SourcePlayer, SourcePlayer.id == PlayerLink.source_player_id)
            .where(SourcePlayer.display_name == name)
        )
    )


def resolve(session: Session, tier_b: bool | None = None) -> identity_auto.Report:
    generate_candidates(session)
    if tier_b is not None:
        identity_auto.TIER_B_MIN_SAMPLES = 0
        identity_auto.TIER_B_MAX_FALSE_LINK_RATE = 1.0 if tier_b else -1.0
    return identity_auto.resolve(session)


@pytest.fixture(autouse=True)
def tier_b_threshold() -> Any:
    saved = identity_auto.TIER_B_MIN_SAMPLES, identity_auto.TIER_B_MAX_FALSE_LINK_RATE
    yield
    identity_auto.TIER_B_MIN_SAMPLES, identity_auto.TIER_B_MAX_FALSE_LINK_RATE = saved


def test_same_member_id_from_the_same_issuer_is_linked_across_sources(
    session: Session,
) -> None:
    play(session, T1, [row(side1=(("1", "Robin SAMPLE", "QA-1001"),))])
    play(session, T2, [row(side1=(("9", "Robin SAMPLE", "qa1001"),))], source=BA)
    report = resolve(session)
    # Robin, and the fixture's default opponent (same member id under both sources too)
    assert report.outcomes["linked:tier A"] == 2
    assert len(player_of(session, "Robin SAMPLE")) == 1


def test_namesakes_with_different_member_ids_are_never_merged(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Chris COMMON", "QA1111"),))])
    play(session, T2, [row(side1=(("2", "Chris COMMON", "QA2222"),))])
    report = resolve(session, tier_b=True)
    assert report.outcomes["deferred"] >= 1
    assert not any(k.startswith("linked") for k in report.outcomes)
    assert len(player_of(session, "Chris COMMON")) == 2
    # deferred, not lost: kept with its reason, and not generated again
    c = session.scalars(select(IdentityCandidate).filter_by(status="deferred")).first()
    assert c is not None and "different member ids" in (c.note or "")
    assert generate_candidates(session) == 0


def test_two_entries_in_one_tournament_are_distinct(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Sam TWIN", None),), side2=(("2", "Sam TWIN", None),))])
    report = resolve(session, tier_b=True)
    assert report.outcomes["distinct"] == 1
    assert len(player_of(session, "Sam TWIN")) == 2


def _member_and_unnamed(session: Session, shared_partner: bool, namesake: bool = False) -> None:
    """A member in T1 and, in T2, a record with no member id but the same name."""
    partner = ("50", "Pat PARTNER", "QA5050")
    play(session, T1, [doubles(1, (("1", "Lee UNIQUE", "QA1"), partner), (CLUB[0], CLUB[1]))])
    other_partner = partner if shared_partner else ("51", "Someone ELSE", "QA5151")
    play(session, T2, [
        doubles(1, (("7", "Lee UNIQUE", None), other_partner), (CLUB[0], CLUB[1])),
        doubles(2, (CLUB[2], CLUB[3]), (("60", "Kim FILLER", "QA60"), ("61", "Jo FILLER", "QA61"))),
    ])  # fmt: skip
    if namesake:
        play(session, T3, [row(side1=(("3", "Lee UNIQUE", "QA3"),))])


def test_tier_b_links_with_a_shared_partner(session: Session) -> None:
    _member_and_unnamed(session, shared_partner=True)
    report = resolve(session, tier_b=True)
    assert report.outcomes["linked:tier B"] == 1
    assert len(player_of(session, "Lee UNIQUE")) == 1


def test_tier_b_without_corroboration_defers(session: Session) -> None:
    _member_and_unnamed(session, shared_partner=False)
    resolve(session, tier_b=True)
    assert len(player_of(session, "Lee UNIQUE")) == 2


def test_tier_b_defers_when_the_issuer_has_namesakes(session: Session) -> None:
    _member_and_unnamed(session, shared_partner=True, namesake=True)
    resolve(session, tier_b=True)
    assert len(player_of(session, "Lee UNIQUE")) == 3


def test_tier_b_is_off_until_evaluated(session: Session) -> None:
    _member_and_unnamed(session, shared_partner=True)
    report = resolve(session, tier_b=False)
    assert not report.tier_b_enabled
    assert len(player_of(session, "Lee UNIQUE")) == 2


def test_a_deferred_pair_is_linked_when_evidence_arrives(session: Session) -> None:
    _member_and_unnamed(session, shared_partner=False)
    resolve(session, tier_b=True)
    assert len(player_of(session, "Lee UNIQUE")) == 2
    # a later tournament shows the unnamed record playing with the member's partner
    unnamed = session.scalars(select(SourcePlayer).filter_by(display_name="Lee UNIQUE").where(
        SourcePlayer.source_key.like("tplayer:%"))).one()  # fmt: skip
    play(session, T2, [doubles(3, (("7", "Lee UNIQUE", None), ("50", "Pat PARTNER", "QA5050")),
                               (CLUB[2], CLUB[3]))])  # fmt: skip
    assert unnamed.source_key.startswith("tplayer:")
    resolve(session, tier_b=True)
    assert len(player_of(session, "Lee UNIQUE")) == 1


def test_withheld_players_are_never_linked(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Robin SAMPLE", "QA-1001"),))])
    play(session, T2, [row(side1=(("9", "Robin SAMPLE", "qa1001"),))], source=BA)
    for p in session.scalars(select(Player)):
        if p.display_name == "Robin SAMPLE":
            p.withheld_at = datetime.now(UTC)
            break
    resolve(session)
    assert len(player_of(session, "Robin SAMPLE")) == 2


def test_an_automatic_link_can_be_undone(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Robin SAMPLE", "QA-1001"),))])
    play(session, T2, [row(side1=(("9", "Robin SAMPLE", "qa1001"),))], source=BA)
    resolve(session)
    robin = select(SourcePlayer.id).filter_by(display_name="Robin SAMPLE")
    c = session.scalars(
        select(IdentityCandidate)
        .filter_by(status="accepted")
        .where(IdentityCandidate.source_player_a_id.in_(robin))
    ).one()
    assert c.decision_id is not None
    identity.undo(session, c.decision_id, "test", "human:tester")
    assert len(player_of(session, "Robin SAMPLE")) == 2


def test_tier_b_links_are_reverted_when_it_is_disabled(session: Session) -> None:
    _member_and_unnamed(session, shared_partner=True)
    resolve(session, tier_b=True)
    assert len(player_of(session, "Lee UNIQUE")) == 1
    report = resolve(session, tier_b=False)
    assert report.outcomes["reverted:tier B"] == 1
    assert len(player_of(session, "Lee UNIQUE")) == 2


def test_a_persons_undo_is_not_relinked_by_the_next_pass(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Robin SAMPLE", "QA-1001"),))])
    play(session, T2, [row(side1=(("9", "Robin SAMPLE", "QA-1001"),))], source=BA)
    resolve(session)
    robin = select(SourcePlayer.id).filter_by(display_name="Robin SAMPLE")
    c = session.scalars(
        select(IdentityCandidate).where(IdentityCandidate.source_player_a_id.in_(robin))
    ).one()
    assert c.decision_id is not None
    identity.undo(session, c.decision_id, "wrong link", "human:tester")
    resolve(session)
    assert len(player_of(session, "Robin SAMPLE")) == 2


def test_ids_equal_only_without_punctuation_need_the_same_name(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Ann ONE", "1.2345"),))])
    play(session, T2, [row(side1=(("9", "Ann TWO", "12.345"),))], source=BA)
    resolve(session)
    assert len(player_of(session, "Ann ONE") | player_of(session, "Ann TWO")) == 2


def test_placeholder_member_ids_identify_nobody(session: Session) -> None:
    play(session, T1, [row(side1=(("1", "Pat DASH", "-"),), side2=(("2", "Lou DASH", "-"),))])
    keys = set(session.scalars(select(SourcePlayer.source_key).where(
        SourcePlayer.display_name.in_(["Pat DASH", "Lou DASH"]))))  # fmt: skip
    assert len(keys) == 2 and all(k.startswith("tplayer:") for k in keys)


def test_a_link_is_refused_when_the_players_share_a_tournament(session: Session) -> None:
    # Robin A (T1) and Robin B (T2) carry the same member id, but player B already holds a
    # record from T1 through an earlier link: merging would put two entries in one tournament
    robin, other = ("1", "Robin SAMPLE", "QA-1001"), ("5", "Other X", None)
    play(session, T1, [row(side1=(robin,), side2=(other,))])
    play(session, T2, [row(side1=(("9", "Robin SAMPLE", "QA-1001"),))], source=BA)
    t1_other = session.scalars(select(SourcePlayer).filter_by(display_name="Other X")).one()
    robin_b = session.scalars(
        select(SourcePlayer).filter_by(display_name="Robin SAMPLE", source_id=BA)
    ).one()
    link_b = session.get(PlayerLink, robin_b.id)
    link_other = session.get(PlayerLink, t1_other.id)
    assert link_b and link_other
    link_other.player_id = link_b.player_id  # as if a person had linked them
    session.flush()
    report = resolve(session)
    assert report.outcomes["distinct"] >= 1
    assert len(player_of(session, "Robin SAMPLE")) == 2
