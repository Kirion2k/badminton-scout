"""Data-quality evidence for rating (ADR-0012). Read-only; reports counts, never names.

The BWF compilation names players without stable ids, so one name can be two people (or one
person under two spellings is two names). Nothing here merges or splits anyone (ADR-0003): it
flags players whose records are physically impossible for one person, so the report can show how
results change without them.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, text

from scout.analytics.graph import UnionFind
from scout.analytics.ordering import round_rank
from scout.ratings.dataset import BWF_SOURCE, Row

_QUAL_UNKNOWN, _GROUP = round_rank("Q"), round_rank("Group A")


@dataclass
class IdentityAudit:
    players: int = 0
    # one player key in two different tournaments on the same day
    two_tournaments_same_day: set[int] = field(default_factory=set[int])
    # one player key in both men's and women's singles
    both_genders: set[int] = field(default_factory=set[int])
    # one player key twice in one knockout round of an event (two entries under one name)
    twice_in_a_round: set[int] = field(default_factory=set[int])

    @property
    def flagged(self) -> set[int]:
        return self.two_tournaments_same_day | self.both_genders | self.twice_in_a_round


_APPEARANCES = """
    with recursive up(id, root) as (
        select id, id from player where merged_into_id is null
        union all
        select p.id, up.root from player p join up on p.merged_into_id = up.id)
    select up.root, t.id, m.played_on, e.discipline, e.id, coalesce(m.round, ''), m.id
    from match m
    join event e on e.id = m.event_id
    join tournament t on t.id = e.tournament_id
    join match_side ms on ms.match_id = m.id
    join match_side_player msp on msp.match_side_id = ms.id
    join player_link pl on pl.source_player_id = msp.source_player_id
    join up on up.id = pl.player_id
    where t.source_id = :source
"""


def identity(conn: Connection, source: str = BWF_SOURCE) -> IdentityAudit:
    tournaments_on: defaultdict[tuple[int, date], set[int]] = defaultdict(set)
    singles: defaultdict[int, set[str]] = defaultdict(set)
    in_round: Counter[tuple[int, int, str]] = Counter()
    players: set[int] = set()
    for player, tid, day, disc, eid, rnd, _ in conn.execute(text(_APPEARANCES), {"source": source}):
        players.add(player)
        tournaments_on[(player, day)].add(tid)
        if disc in ("MS", "WS"):
            singles[player].add(disc)
        # knockout rounds only: in a group, or a bare "Q", several matches are normal
        if round_rank(rnd) not in (None, _QUAL_UNKNOWN, _GROUP):
            in_round[(player, eid, rnd)] += 1
    audit = IdentityAudit(players=len(players))
    audit.two_tournaments_same_day = {p for (p, _), ts in tournaments_on.items() if len(ts) > 1}
    audit.both_genders = {p for p, d in singles.items() if len(d) > 1}
    audit.twice_in_a_round = {p for (p, _, _), n in in_round.items() if n > 1}
    return audit


def _key(name: str) -> str:
    """Names compared loosely: accents, case and punctuation ignored."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(sorted(re.findall(r"[a-z]+", plain.lower())))


_SINGLES = """
    select t.source_id, m.played_on, e.discipline,
           string_agg(sp.display_name, '|' order by ms.side)
    from match m
    join event e on e.id = m.event_id and e.discipline in ('MS', 'WS')
    join tournament t on t.id = e.tournament_id
    join match_side ms on ms.match_id = m.id
    join match_side_player msp on msp.match_side_id = ms.id
    join source_player sp on sp.id = msp.source_player_id
    where t.source_id = :bwf
       or (t.source_id like 'tournamentsoftware%%' and m.played_on between :lo and :hi)
    group by m.id, t.source_id, m.played_on, e.discipline
"""


def cross_source_duplicates(conn: Connection, window_days: int = 1) -> dict[str, int]:
    """Singles matches that appear in both the BWF compilation and a Tournament Software source:
    the same discipline, both players' names, and dates within `window_days`. They never share a
    rating pool, so a duplicate inflates nothing; this measures the overlap."""
    lo, hi = conn.execute(
        text(
            "select min(m.played_on), max(m.played_on) from match m join event e"
            " on e.id = m.event_id join tournament t on t.id = e.tournament_id"
            " where t.source_id = :s"
        ),
        {"s": BWF_SOURCE},
    ).one()
    bwf: defaultdict[tuple[str, str], list[date]] = defaultdict(list)
    ts: list[tuple[str, str, date]] = []
    rows = conn.execute(text(_SINGLES), {"bwf": BWF_SOURCE, "lo": lo, "hi": hi})
    for source, day, disc, names in rows:
        pair = "/".join(sorted(_key(n) for n in str(names).split("|")))
        if source == BWF_SOURCE:
            bwf[(disc, pair)].append(day)
        else:
            ts.append((disc, pair, day))
    window = timedelta(days=window_days)
    found = sum(
        1 for disc, pair, day in ts
        if any(abs(d - day) <= window for d in bwf.get((disc, pair), ()))
    )  # fmt: skip
    return {"ts_singles_in_bwf_span": len(ts), "also_in_bwf": found}


def connectivity(rows: Iterable[Row], source_of: dict[int, str]) -> dict[str, dict[str, Any]]:
    """Per pool: who can be compared with whom through played matches. `source_of` maps a
    tournament id to its source; a player's home is the source where they played most."""
    by_pool: defaultdict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_pool[r.pool].append(r)
    out: dict[str, dict[str, Any]] = {}
    for pool, prs in sorted(by_pool.items()):
        uf = UnionFind()
        played: Counter[int] = Counter()
        homes: defaultdict[int, Counter[str]] = defaultdict(Counter)
        for r in prs:
            uf.union(r.a, r.b)
            for p in (r.a, r.b):
                played[p] += 1
                homes[p][source_of[r.cluster]] += 1
        home = {p: c.most_common(1)[0][0] for p, c in homes.items()}
        sizes = Counter(uf.find(p) for p in played)
        ranked = sorted(sizes.values(), reverse=True)
        n = len(played)
        largest_root = max(sizes, key=lambda root: sizes[root])
        in_largest = [p for p in played if uf.find(p) == largest_root]
        cross = sum(1 for r in prs if home[r.a] != home[r.b])
        # what share of all player pairs could be compared at all (same component)
        pairs = sum(s * (s - 1) for s in ranked) / (n * (n - 1)) if n > 1 else 0.0
        out[pool] = {
            "players": n,
            "matches": len(prs),
            "components": len(ranked),
            "largest": ranked[:5],
            "share_in_largest": len(in_largest) / n if n else 0.0,
            "comparable_pair_share": pairs,
            "players_with_one_match": sum(1 for c in played.values() if c == 1),
            "players_with_10_plus": sum(1 for c in played.values() if c >= 10),
            "cross_home_matches": cross,
            "largest_by_home": dict(Counter(home[p] for p in in_largest).most_common()),
            "homes_reaching_largest": sorted({home[p] for p in in_largest}),
            "homes": dict(Counter(home.values()).most_common()),
        }
    return out
