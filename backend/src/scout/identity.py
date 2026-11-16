"""Identity decisions (ADR-0003, ADR-0011): merge, reject and undo, each recorded and reversible.
Humans may decide any candidate; `identity_auto` decides only on stable identifiers or corroborated
evidence, never on name similarity alone."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scout.fixtures.providers import FIXTURE_SOURCES
from scout.models import IdentityCandidate, IdentityDecision, Player, PlayerLink, SourcePlayer


def name_key(name: str) -> str:
    """Case and word order don't matter ("KIM Yong Hyun" == "Yong Hyun KIM")."""
    return " ".join(sorted(name.casefold().split()))


def generate_candidates(session: Session) -> int:
    """Source-player pairs with the same name key but different identities; returns new pairs."""
    groups: dict[tuple[str, str], list[int]] = {}
    for sp_id, source_id, name in session.execute(
        select(SourcePlayer.id, SourcePlayer.source_id, SourcePlayer.display_name)
    ):
        groups.setdefault((source_id, name_key(name)), []).append(sp_id)
    pairs = [
        {"source_player_a_id": a, "source_player_b_id": b, "rule": "same_name_different_id"}
        for ids in groups.values()
        for i, a in enumerate(sorted(ids))
        for b in sorted(ids)[i + 1 :]
    ]
    if not pairs:
        return 0
    before = session.scalar(select(func.count()).select_from(IdentityCandidate)) or 0
    session.execute(insert(IdentityCandidate).values(pairs).on_conflict_do_nothing())
    session.flush()
    return (session.scalar(select(func.count()).select_from(IdentityCandidate)) or 0) - before


def _links(session: Session, player_ids: list[int]) -> dict[str, Any]:
    links = session.execute(
        select(PlayerLink.source_player_id, PlayerLink.player_id).where(
            PlayerLink.player_id.in_(player_ids)
        )
    ).all()
    merged = session.execute(
        select(Player.id, Player.merged_into_id).where(Player.id.in_(player_ids))
    ).all()
    return {
        "links": {str(sp): p for sp, p in links},
        "merged_into": {str(p): m for p, m in merged},
    }


def player_of(session: Session, source_player_id: int) -> int:
    player = session.scalar(
        select(PlayerLink.player_id).where(PlayerLink.source_player_id == source_player_id)
    )
    if player is None:
        raise ValueError(f"source player {source_player_id} is not linked")
    return player


def merge(
    session: Session,
    candidate_id: int,
    reason: str,
    decided_by: str,
    *,
    allow_deferred: bool = False,
    keep_b: bool = False,
) -> IdentityDecision:
    """Merge candidate b's player into a's (a's into b's with `keep_b`). Reversible with `undo`."""
    c = session.get(IdentityCandidate, candidate_id)
    if c is None or c.status not in (("open", "deferred") if allow_deferred else ("open",)):
        raise ValueError(f"candidate {candidate_id} is not open")
    keep = player_of(session, c.source_player_a_id)
    gone = player_of(session, c.source_player_b_id)
    if keep_b:
        keep, gone = gone, keep
    if keep == gone:
        raise ValueError("already the same player")
    if any(p and p.withheld_at for p in (session.get(Player, keep), session.get(Player, gone))):
        # a merge would move a withheld person's matches onto a visible profile (ADR-0010)
        raise ValueError("one side is withheld after a removal request: restore it first")
    earlier = list(session.scalars(select(Player.id).where(Player.merged_into_id == gone)))
    touched = [keep, gone, *earlier]  # everything this merge changes, so undo can restore it
    before = _links(session, touched)
    for link in session.scalars(select(PlayerLink).where(PlayerLink.player_id == gone)):
        link.player_id = keep
    player = session.get(Player, gone)
    if player is not None:
        player.merged_into_id = keep
    # keep chains one hop long: players merged into `gone` earlier now point at `keep`
    for earlier in session.scalars(select(Player).where(Player.merged_into_id == gone)):
        earlier.merged_into_id = keep
    session.flush()
    decision = IdentityDecision(
        action="merge",
        before=before,
        after=_links(session, touched),
        reason=reason,
        decided_by=decided_by,
    )
    session.add(decision)
    session.flush()
    for link in session.scalars(select(PlayerLink).where(PlayerLink.player_id == keep)):
        link.decision_id = decision.id
    c.status, c.decision_id = "accepted", decision.id
    session.flush()
    return decision


def reject(
    session: Session,
    candidate_id: int,
    reason: str,
    decided_by: str,
    *,
    allow_deferred: bool = False,
) -> IdentityDecision:
    c = session.get(IdentityCandidate, candidate_id)
    if c is None or c.status not in (("open", "deferred") if allow_deferred else ("open",)):
        raise ValueError(f"candidate {candidate_id} is not open")
    decision = IdentityDecision(
        action="reject",
        before={"candidate": candidate_id},
        reason=reason,
        decided_by=decided_by,
    )
    session.add(decision)
    session.flush()
    c.status, c.decision_id = "rejected", decision.id
    session.flush()
    return decision


def undo(session: Session, decision_id: int, reason: str, decided_by: str) -> IdentityDecision:
    """Restore the links a merge replaced. History is kept: the undo is its own decision."""
    d = session.get(IdentityDecision, decision_id)
    if d is None or d.action != "merge":
        raise ValueError(f"decision {decision_id} is not a merge")
    players = [int(p) for p in d.before["merged_into"]]
    current = _links(session, players)
    if current != d.after:
        # a later decision touched these players (or this merge was already undone): undoing
        # now would silently revert that one too
        raise ValueError(f"decision {decision_id} is no longer the current state; undo later ones")
    split = IdentityDecision(
        action="split", before=current, after=d.before, reason=reason, decided_by=decided_by
    )
    session.add(split)
    session.flush()
    for sp, player_id in d.before["links"].items():
        link = session.get(PlayerLink, int(sp))
        if link is not None:
            link.player_id, link.decision_id = player_id, split.id
    for p, merged_into in d.before["merged_into"].items():
        player = session.get(Player, int(p))
        if player is not None:
            player.merged_into_id = merged_into
    reopened = session.scalars(
        select(IdentityCandidate).where(IdentityCandidate.decision_id == decision_id)
    )
    for c in reopened:
        if decided_by.startswith("auto:"):
            # the resolver withdrawing its own link: back to deferred, open to new evidence
            c.status, c.decision_id, c.note = "deferred", None, "automatic link withdrawn"
        else:
            # a person undid it: final, or the next automatic pass would link it again
            c.status, c.decision_id, c.note = "rejected", split.id, f"undone by a person: {reason}"
    session.flush()
    return split


def link_fixture_player(
    session: Session, source_player_id: int, player_id: int, reason: str, decided_by: str
) -> IdentityDecision:
    """A person's decision that a fixture provider's player is an existing (rated) player: a
    candidate plus a merge into that player, so it is audited and can be undone (ADR-0014)."""
    if not decided_by.strip() or decided_by.startswith(("system", "auto")):
        raise ValueError("a fixture player is linked by a person")
    target = session.get(Player, player_id)
    if target is None or target.merged_into_id is not None or target.withheld_at is not None:
        raise ValueError(f"player {player_id} is not a current, published player")
    sp = session.get(SourcePlayer, source_player_id)
    if sp is None or sp.source_id not in FIXTURE_SOURCES:
        # other sources' identities go through candidate review (ADR-0003, ADR-0011)
        raise ValueError(f"source player {source_player_id} is not from a fixture source")
    own = player_of(session, source_player_id)
    if own == player_id:
        raise ValueError("already linked to that player")
    if session.scalar(select(func.count()).select_from(PlayerLink)
                      .where(PlayerLink.player_id == own)) != 1:  # fmt: skip
        # its record already holds other identities: merging it would merge two people
        raise ValueError(f"source player {source_player_id} is already linked: undo that first")
    other = session.scalar(
        select(func.min(PlayerLink.source_player_id)).where(PlayerLink.player_id == player_id)
    )
    if other is None:
        raise ValueError(f"player {player_id} has no source records")
    a, b = sorted((source_player_id, other))
    c = session.scalar(
        select(IdentityCandidate).filter_by(source_player_a_id=a, source_player_b_id=b)
    )
    if c is None:
        c = IdentityCandidate(source_player_a_id=a, source_player_b_id=b, rule="fixture_link")
        session.add(c)
        session.flush()
    elif c.status == "accepted":
        raise ValueError(f"candidate {c.id} for this pair is already accepted")
    else:  # a new decision by a person reopens an earlier rejection or deferral
        c.status, c.decision_id = "open", None
    # keep the existing player: the fixture player's empty record is the one merged away
    return merge(session, c.id, reason, decided_by, keep_b=other == b)
