"""ADR-0003: candidates are suggestions; merges are human, audited and exactly reversible."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import identity
from scout.models import IdentityCandidate, IdentityDecision, Player, PlayerLink, SourcePlayer

from .test_ts_ingest import ingest
from .ts_fixtures import row

pytestmark = pytest.mark.db


def links(session: Session) -> dict[int, int]:
    return dict(session.execute(select(PlayerLink.source_player_id, PlayerLink.player_id)).all())


def seed(session: Session) -> None:
    # same person twice? same name, different member ids, word order differs
    ingest(session, [
        row(),
        row(draw=8, side1=(("301", "TESTER Alex", "QA9999"),), side2=(("302", "Pat D", "QA3"),)),
    ])  # fmt: skip


def test_name_key_ignores_case_and_word_order() -> None:
    assert identity.name_key("KIM Yong Hyun") == identity.name_key("yong hyun  kim")
    assert identity.name_key("Yu Chen CHANG") != identity.name_key("Yu-Chang CHEN")


def test_candidates_are_suggested_not_applied(session: Session) -> None:
    seed(session)
    before = links(session)
    assert identity.generate_candidates(session) == 1
    assert identity.generate_candidates(session) == 0  # idempotent
    assert links(session) == before  # nothing merged automatically


def test_merge_then_undo_restores_exact_links(session: Session) -> None:
    seed(session)
    identity.generate_candidates(session)
    original = links(session)
    candidate = session.scalars(select(IdentityCandidate)).one()
    merge = identity.merge(session, candidate.id, "same DOB per club", "human:test")
    merged = links(session)
    assert len(set(merged.values())) == len(set(original.values())) - 1
    gone = next(p for p in set(original.values()) - set(merged.values()))
    assert session.get(Player, gone).merged_into_id is not None  # type: ignore[union-attr]

    identity.undo(session, merge.id, "different people after all", "human:test")
    assert links(session) == original
    assert session.get(Player, gone).merged_into_id is None  # type: ignore[union-attr]
    # a person's undo is final: the automatic resolver must not link the pair again (ADR-0011)
    assert session.get(IdentityCandidate, candidate.id).status == "rejected"  # type: ignore[union-attr]
    actions = session.scalars(select(IdentityDecision.action).order_by(IdentityDecision.id)).all()
    assert actions[-2:] == ["merge", "split"]  # history kept, never edited


def test_rejected_candidate_cannot_be_merged(session: Session) -> None:
    seed(session)
    identity.generate_candidates(session)
    c = session.scalars(select(IdentityCandidate)).one()
    identity.reject(session, c.id, "different clubs and ages", "human:test")
    with pytest.raises(ValueError, match="not open"):
        identity.merge(session, c.id, "x", "human:test")


def test_source_identities_are_never_rewritten(session: Session) -> None:
    seed(session)
    identity.generate_candidates(session)
    keys = set(session.scalars(select(SourcePlayer.source_key)).all())
    c = session.scalars(select(IdentityCandidate)).one()
    identity.merge(session, c.id, "test", "human:test")
    assert set(session.scalars(select(SourcePlayer.source_key)).all()) == keys


def test_undo_refuses_when_a_later_merge_touched_the_same_players(session: Session) -> None:
    seed(session)
    ingest(session, [row(draw=9, side1=(("401", "alex tester", "QA7777"),),
                         side2=(("402", "Pat D", "QA3"),))])  # fmt: skip
    identity.generate_candidates(session)
    ordered = select(IdentityCandidate).order_by(IdentityCandidate.id)
    first, second = session.scalars(ordered).all()[:2]
    m1 = identity.merge(session, first.id, "one", "human:test")
    m2 = identity.merge(session, second.id, "two", "human:test")
    with pytest.raises(ValueError, match="no longer the current state"):
        identity.undo(session, m1.id, "x", "human:test")
    identity.undo(session, m2.id, "undo latest first", "human:test")
    identity.undo(session, m1.id, "then the earlier one", "human:test")
    with pytest.raises(ValueError, match="no longer the current state"):
        identity.undo(session, m1.id, "twice", "human:test")
