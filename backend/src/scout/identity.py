"""Human-reviewed identity merges (ADR-0003): candidates are suggested, never auto-applied."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

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


def _player_of(session: Session, source_player_id: int) -> int:
    player = session.scalar(
        select(PlayerLink.player_id).where(PlayerLink.source_player_id == source_player_id)
    )
    if player is None:
        raise ValueError(f"source player {source_player_id} is not linked")
    return player


def merge(session: Session, candidate_id: int, reason: str, decided_by: str) -> IdentityDecision:
    """Merge candidate b's player into a's. Reversible with `undo`."""
    c = session.get(IdentityCandidate, candidate_id)
    if c is None or c.status != "open":
        raise ValueError(f"candidate {candidate_id} is not open")
    keep = _player_of(session, c.source_player_a_id)
    gone = _player_of(session, c.source_player_b_id)
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


def reject(session: Session, candidate_id: int, reason: str, decided_by: str) -> IdentityDecision:
    c = session.get(IdentityCandidate, candidate_id)
    if c is None or c.status != "open":
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
        c.status, c.decision_id = "open", None
    session.flush()
    return split
