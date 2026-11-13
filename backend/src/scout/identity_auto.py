"""Automatic identity resolution (ADR-0011): link only on evidence, keep doubt as separate records.

Tiers, strictest first:
- A, deterministic: the same member id from the same issuing organisation (case and punctuation
  ignored), in any source. Linked, unless a conflict says otherwise.
- Conflict: two records that played in the same tournament are two entries, so they are distinct.
- B, corroborated: a record without a member id (tournament-scoped) and a member record. Linked only
  when the names match exactly, the tournament's issuer is the member's issuer, the name is
  unique among that issuer's members, and the two share a doubles partner. Enabled only while
  `evaluate()` measures no false link on member ground truth.
- Everything else is deferred: kept as separate records, re-checked whenever this runs.

Nothing here merges on a similarity score; every link is an IdentityDecision that `undo` reverts.
"""

import math
import re
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scout import identity
from scout.identity import name_key
from scout.models import (
    Event,
    IdentityCandidate,
    Match,
    MatchSide,
    MatchSidePlayer,
    Player,
    PlayerLink,
    SourcePlayer,
)

DECIDED_BY = "auto:identity-resolver"
Verdict = Literal["link", "distinct", "defer"]


def member_parts(source_key: str) -> tuple[str, str] | None:
    """(issuer, exact member id) of a member key: percent-decoding, case and invisible characters
    ignored, nothing else. None for tournament-scoped records and placeholder ids ("-")."""
    if not source_key.startswith("member:"):
        return None
    issuer, _, member = source_key[len("member:") :].partition("/")
    exact = " ".join(re.sub(r"[\u00a0\u200b-\u200d\u2060\ufeff]", " ",
                            urllib.parse.unquote_plus(member)).casefold().split())  # fmt: skip
    exact = re.sub(r"~\d+$", "", exact)  # a duplicate marked by `scout privacy minimise`
    return (issuer.lower(), exact) if re.search(r"[0-9a-z]", exact) else None


def loose(member: str) -> str:
    """Letters and digits only: "QA-1001" and "qa1001". Equal only this way, two ids need the same
    name as well before they link ("1.2345" and "12.345" must not)."""
    return re.sub(r"[^0-9a-z]", "", member)


@dataclass
class Evidence:
    """What the resolver knows about every source player, built once per run."""

    keys: dict[int, str]
    names: dict[int, str]  # name_key
    tournaments: dict[int, set[int]]
    partners: dict[int, dict[int, set[str]]]  # source player -> tournament -> partner name keys
    issuer_of_tournament: dict[int, str]  # dominant member issuer, when one clearly dominates
    members_by_issuer_name: dict[tuple[str, str], set[int]]


def gather(session: Session) -> Evidence:
    keys: dict[int, str] = {}
    names: dict[int, str] = {}
    for sp_id, key, name in session.execute(
        select(SourcePlayer.id, SourcePlayer.source_key, SourcePlayer.display_name)
    ):
        keys[sp_id], names[sp_id] = key, name_key(name)
    tournaments: dict[int, set[int]] = defaultdict(set)
    sides: dict[int, list[int]] = defaultdict(list)
    side_tournament: dict[int, int] = {}
    for side_id, sp_id, tournament_id in session.execute(
        select(MatchSide.id, MatchSidePlayer.source_player_id, Event.tournament_id)
        .join(MatchSidePlayer, MatchSidePlayer.match_side_id == MatchSide.id)
        .join(Match, Match.id == MatchSide.match_id)
        .join(Event, Event.id == Match.event_id)
    ):
        tournaments[sp_id].add(tournament_id)
        sides[side_id].append(sp_id)
        side_tournament[side_id] = tournament_id
    partners: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for side_id, players in sides.items():
        for p in players:
            for q in players:
                if p != q:
                    partners[p][side_tournament[side_id]].add(names[q])
    issuers: dict[int, Counter[str]] = defaultdict(Counter)
    for sp_id, ts in tournaments.items():
        parts = member_parts(keys[sp_id])
        if parts:
            for t in ts:
                issuers[t][parts[0]] += 1
    issuer_of_tournament: dict[int, str] = {}
    for t, counts in issuers.items():
        issuer, n = counts.most_common(1)[0]
        if n >= 5 and n >= 0.9 * sum(counts.values()):
            issuer_of_tournament[t] = issuer
    members: dict[tuple[str, str], set[int]] = defaultdict(set)
    for sp_id, key in keys.items():
        parts = member_parts(key)
        if parts:
            members[(parts[0], names[sp_id])].add(sp_id)
    return Evidence(keys, names, tournaments, partners, issuer_of_tournament, members)


def classify(ev: Evidence, a: int, b: int, tier_b: bool) -> tuple[Verdict, str]:
    if ev.tournaments.get(a, set()) & ev.tournaments.get(b, set()):
        return "distinct", "both played in the same tournament: two entries"
    pa, pb = member_parts(ev.keys[a]), member_parts(ev.keys[b])
    if pa and pb:
        if pa == pb:
            return "link", "tier A: same member id from the same issuer"
        if pa[0] == pb[0] and loose(pa[1]) == loose(pb[1]) and ev.names[a] == ev.names[b]:
            return "link", "tier A: same member id (written differently) and same name"
        return "defer", "different member ids: one person registered twice, or two people"
    known = pa or pb
    if known is not None and tier_b:
        member, other = (a, b) if pa else (b, a)
        why = _tier_b(ev, member, other, known[0])
        if why is None:
            return "link", "tier B: same name and issuer, unique in the issuer, a shared partner"
        return "defer", why
    return "defer", "no stable identifier on either record"


def _tier_b(ev: Evidence, member: int, other: int, issuer: str) -> str | None:
    """None when the corroborated rule holds; otherwise why it does not."""
    if ev.names[member] != ev.names[other]:
        return "names differ"
    if any(ev.issuer_of_tournament.get(t) != issuer for t in ev.tournaments.get(other, set())):
        return "the other record's tournaments are not clearly the member's issuer's"
    if len(ev.members_by_issuer_name[(issuer, ev.names[member])]) != 1:
        return "several members of this issuer share the name"
    theirs = {n for ns in ev.partners[other].values() for n in ns}
    ours = {n for ns in ev.partners[member].values() for n in ns}
    if not theirs & ours:
        return "no shared doubles partner"
    return None


@dataclass
class Evaluation:
    """Tier B measured on labelled member data (member ids are the ground truth).

    Positives: one member's appearances in two tournaments; the rule should accept them.
    Negatives: two different member ids from one issuer with the same name; the rule must reject
    them. Uniqueness alone would make precision trivially perfect, so the negatives test the
    corroborating evidence (a shared partner) without it."""

    positives: int
    positives_accepted: int
    negatives: int
    negatives_accepted: int  # false links the evidence would make

    @property
    def recall(self) -> float:
        return self.positives_accepted / self.positives if self.positives else 0.0

    @property
    def false_link_rate(self) -> float:
        return self.negatives_accepted / self.negatives if self.negatives else 1.0

    @property
    def false_link_upper_bound(self) -> float:
        """95% Wilson upper bound: zero errors in 200 samples still allows about 1.9%."""
        n = self.negatives
        if not n:
            return 1.0
        p, z = self.false_link_rate, 1.96
        centre = p + z * z / (2 * n)
        spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        return (centre + spread) / (1 + z * z / n)


def evaluate(ev: Evidence) -> Evaluation:
    def partners(sp: int, skip: int | None = None) -> set[str]:
        return {n for t, ns in ev.partners[sp].items() if t != skip for n in ns}

    pos = pos_ok = neg = neg_ok = 0
    for members in ev.members_by_issuer_name.values():
        for m in members:
            doubles = [t for t, ns in ev.partners[m].items() if ns]
            for t in doubles if len(doubles) > 1 else []:
                pos += 1
                pos_ok += bool(ev.partners[m][t] & partners(m, skip=t))
        ordered = sorted(members)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if partners(a) and partners(b):
                    neg += 1
                    neg_ok += bool(partners(a) & partners(b))
    return Evaluation(pos, pos_ok, neg, neg_ok)


# Tier B runs only if, on at least this many labelled negatives, its evidence would wrongly link
# at most this share. Measured on real data 2026-11-13: 47% (disabled).
TIER_B_MIN_SAMPLES = 200
TIER_B_MAX_FALSE_LINK_RATE = 0.001


@dataclass
class Report:
    evaluation: Evaluation
    tier_b_enabled: bool
    outcomes: Counter[str]


def resolve(session: Session) -> Report:
    """Classify every open or deferred candidate; apply links and distinctions as decisions.
    One resolver at a time across all workers: concurrent merges would tangle undo history."""
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(hashtext('scout-identity'))")):
        return Report(Evaluation(0, 0, 0, 0), False, Counter({"skipped:another resolver": 1}))
    _cross_source_candidates(session)
    ev = gather(session)
    evaluation = evaluate(ev)
    tier_b = (
        evaluation.negatives >= TIER_B_MIN_SAMPLES
        and evaluation.false_link_upper_bound <= TIER_B_MAX_FALSE_LINK_RATE
    )
    reverted, still_linked = (0, 0) if tier_b else _revert_tier_b(session)
    outcomes: Counter[str] = Counter()
    if reverted:
        outcomes["reverted:tier B"] = reverted
    if still_linked:
        outcomes["tier B links kept (later decisions depend on them)"] = still_linked
    rows = session.scalars(
        select(IdentityCandidate).where(IdentityCandidate.status.in_(["open", "deferred"]))
    ).all()
    for c in rows:
        verdict, why = classify(ev, c.source_player_a_id, c.source_player_b_id, tier_b)
        if verdict == "link" and (conflict := _player_conflict(session, ev, c)):
            verdict, why = conflict
        if verdict == "link":
            try:
                identity.merge(session, c.id, why, DECIDED_BY, allow_deferred=True)
            except ValueError as e:  # withheld, or already one player
                c.status, c.note = "deferred", str(e)[:200]
                outcomes["deferred:" + str(e)[:40]] += 1
                continue
            outcomes["linked:" + why.split(":")[0]] += 1
        elif verdict == "distinct":
            identity.reject(session, c.id, why, DECIDED_BY, allow_deferred=True)
            outcomes["distinct"] += 1
        else:
            c.status, c.note = "deferred", why
            outcomes["deferred"] += 1
    session.flush()
    return Report(evaluation, tier_b, outcomes)


def _player_conflict(
    session: Session, ev: Evidence, c: IdentityCandidate
) -> tuple[Verdict, str] | None:
    """A merge joins whole players, so check every record of both: one tournament in common means
    two entries, and a pair someone resolved as distinct blocks the link."""
    links = {
        sp: p
        for sp, p in session.execute(
            select(PlayerLink.source_player_id, PlayerLink.player_id).where(
                PlayerLink.player_id.in_(
                    select(PlayerLink.player_id).where(
                        PlayerLink.source_player_id.in_(
                            [c.source_player_a_id, c.source_player_b_id]
                        )
                    )
                )
            )
        )
    }
    pa, pb = links.get(c.source_player_a_id), links.get(c.source_player_b_id)
    side_a = {sp for sp, p in links.items() if p == pa}
    side_b = {sp for sp, p in links.items() if p == pb}
    tournaments_a = {t for sp in side_a for t in ev.tournaments.get(sp, set())}
    if any(ev.tournaments.get(sp, set()) & tournaments_a for sp in side_b):
        return "distinct", "the two players' records share a tournament: two entries"
    rejected = session.scalar(
        select(IdentityCandidate.id).where(
            IdentityCandidate.status == "rejected",
            or_(
                IdentityCandidate.source_player_a_id.in_(side_a)
                & IdentityCandidate.source_player_b_id.in_(side_b),
                IdentityCandidate.source_player_a_id.in_(side_b)
                & IdentityCandidate.source_player_b_id.in_(side_a),
            ),
        )
    )
    if rejected is not None:
        return "defer", "another pair between these players was resolved as distinct"
    return None


def _revert_tier_b(session: Session) -> tuple[int, int]:
    """Undo automatic Tier B links while Tier B is not validated (newest first, so each undo
    restores the state its merge replaced). Returns (reverted, kept because later decisions
    depend on them); `undo` puts the candidates back to deferred."""
    from scout.models import IdentityDecision

    reverted = blocked = 0
    for d in session.scalars(
        select(IdentityDecision)
        .where(
            IdentityDecision.decided_by == DECIDED_BY,
            IdentityDecision.action == "merge",
            IdentityDecision.reason.startswith("tier B"),
        )
        .order_by(IdentityDecision.id.desc())
    ):
        if session.scalar(
            select(IdentityDecision.id).where(
                IdentityDecision.action == "split", IdentityDecision.before == d.after
            )
        ):
            continue  # already undone
        try:
            identity.undo(session, d.id, "tier B disabled: not validated", DECIDED_BY)
        except ValueError:
            blocked += 1  # a later decision built on it: reported, left for a person
            continue
        reverted += 1
    session.flush()
    return reverted, blocked


def _cross_source_candidates(session: Session) -> None:
    """Tier A across sources: the same issuer and member id seen through two portals."""
    by_member: dict[tuple[str, str], list[int]] = defaultdict(list)
    for sp_id, key in session.execute(select(SourcePlayer.id, SourcePlayer.source_key)):
        parts = member_parts(key)
        if parts:
            by_member[(parts[0], loose(parts[1]))].append(sp_id)
    pairs = [
        {"source_player_a_id": a, "source_player_b_id": b, "rule": "same_member_id"}
        for ids in by_member.values()
        for i, a in enumerate(sorted(ids))
        for b in sorted(ids)[i + 1 :]
    ]
    if pairs:
        session.execute(insert(IdentityCandidate).values(pairs).on_conflict_do_nothing())
        session.flush()


def duplicate_estimate(session: Session) -> int:
    """Unresolved candidates whose two records still sit on different players: an upper bound
    on remaining duplicates, since many are different people with the same name."""
    links = {
        sp: p
        for sp, p in session.execute(select(PlayerLink.source_player_id, PlayerLink.player_id))
    }
    live = set(session.scalars(select(Player.id).where(Player.merged_into_id.is_(None))))
    pairs = select(IdentityCandidate.source_player_a_id, IdentityCandidate.source_player_b_id)
    deferred = session.execute(pairs.where(IdentityCandidate.status == "deferred"))
    return sum(1 for a, b in deferred if links.get(a) != links.get(b) and links.get(a) in live)
