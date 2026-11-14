"""Event codes in the languages Tournament Software portals use (evidence: docs/event-codes.md).

Codes mean different things in different languages: "GD" is girls' doubles in English but mixed
doubles (Gemischtes Doppel) in German and Dutch; German "MD" is girls' doubles (Maedchendoppel).
So a tournament's language is read from the codes its own events use, and a code is only applied
in that language. A code that contradicts the event's players per side is not applied. Anything
unclear stays unclassified: an unknown discipline costs coverage, a wrong one corrupts statistics.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

# code -> (discipline, junior). Junior codes name boys/girls events.
_EN = {
    "MS": ("MS", False), "WS": ("WS", False), "MD": ("MD", False), "WD": ("WD", False),
    "XD": ("XD", False), "MX": ("XD", False), "MXD": ("XD", False),
    "BS": ("MS", True), "GS": ("WS", True), "BD": ("MD", True), "GD": ("WD", True),
}  # fmt: skip
_DE = {
    "HE": ("MS", False), "DE": ("WS", False), "HD": ("MD", False), "DD": ("WD", False),
    "GD": ("XD", False), "MX": ("XD", False), "MIX": ("XD", False), "MIXED": ("XD", False),
    "JE": ("MS", True), "ME": ("WS", True), "JD": ("MD", True), "MD": ("WD", True),
    "HERRENEINZEL": ("MS", False), "DAMENEINZEL": ("WS", False),
    "HERRENDOPPEL": ("MD", False), "DAMENDOPPEL": ("WD", False),
}  # fmt: skip
# English codes with no other meaning in German or Dutch: tournaments there mix them in ("MS A").
# GD and MD are not among them: they are the codes whose meaning differs.
_EN_UNAMBIGUOUS = {k: _EN[k] for k in ("MS", "WS", "WD", "XD", "BS", "GS", "BD")}
_DE.update(_EN_UNAMBIGUOUS)
# Austria (obv): "MD" was seen both as mixed and as girls' doubles, so it is left out there.
_DE_AT = {k: v for k, v in _DE.items() if k != "MD"}
# Flanders (badvla) mixes Dutch and French; the two agree on every shared code.
_NL_FR = {
    "HE": ("MS", False), "DE": ("WS", False), "HD": ("MD", False), "DD": ("WD", False),
    "GD": ("XD", False), "JE": ("MS", True), "ME": ("WS", True),
    "SM": ("MS", False), "SD": ("WS", False), "DM": ("MD", False), "DX": ("XD", False),
    "DMX": ("XD", False), "MX": ("XD", False),
    **_EN_UNAMBIGUOUS,
}  # fmt: skip
_FR_EN = {  # Canada: French and English codes; no shared code disagrees
    **_EN,
    "SM": ("MS", False), "SD": ("WS", False), "DM": ("MD", False), "DD": ("WD", False),
    "DX": ("XD", False),
}  # fmt: skip
_PT = {  # Brazil: simples/dupla masculino/feminino, mista
    "SM": ("MS", False), "SF": ("WS", False), "DM": ("MD", False), "DF": ("WD", False),
    "DX": ("XD", False),
}  # fmt: skip
_ID = {  # Indonesian: tunggal/ganda putra/putri; "anak" (children) events are junior
    "TPA": ("MS", False), "TPI": ("WS", False), "GPA": ("MD", False), "GPI": ("WD", False),
    "TAPA": ("MS", True), "TAPI": ("WS", True), "GAPA": ("MD", True), "GAPI": ("WD", True),
}  # fmt: skip
_PHRASES = [  # whole words, any language: (pattern, discipline, junior)
    (r"simples?\s+filles", "WS", True),
    (r"simples?\s+gar[cç]ons", "MS", True),
    (r"doubles?\s+mixtes?", "XD", False),
    (r"herren\s+doppel", "MD", False),
    (r"damen\s+doppel", "WD", False),
    (r"gemischtes\s+doppel", "XD", False),
]

_GERMAN = {"HE", "DE", "HD", "DD", "JE", "ME", "JD"}
_ENGLISH = {"MS", "WS", "WD", "XD", "BS", "GS", "BD"}

_BY_SOURCE = {
    "tournamentsoftware_dbv": _DE,
    "tournamentsoftware_obv": _DE_AT,
    "tournamentsoftware_badvla": _NL_FR,
    "tournamentsoftware_cbbd": _PT,
    "tournamentsoftware_canada": _FR_EN,
    "tournamentsoftware": {**_EN, **_ID},
}

_JUNIOR = re.compile(
    r"\bsub\s?\d{1,2}|"  # Portuguese "Sub17", often glued to a grade ("Sub17B")
    r"\b(u\s?\d{1,2}|under\s?\d{1,2}|boys?|girls?|juniors?|jeugd|jugend|youth|"
    r"jungen|m[aä]dchen|sch[uü]ler|jugendliche|minimes?|benjamins?|cadets?|cad|ben|juv|pee|"
    r"poussins?|pupilles?|juvenil|infant[oil]+|yr\s?\d+)\b",
    re.IGNORECASE,
)
_PARA = re.compile(
    r"\b(para|wh\s?[12]?|sl\s?[34]|su\s?5|sh\s?6|ss\s?6|wheelchair|rolstoel|rollstuhl)\b",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"[\s\-_/(),.:]+")
_SUFFIX = re.compile(r"^([A-Z]{2,4}?)(?:[A-E]|\d{1,2}|SUB\d{1,2})$")  # SMB, SM12, SMSUB17
_GRADE_PREFIX = re.compile(r"^[A-EO](MS|WS|MD|WD|XD)$")  # Australia: AMS, DXD (grade, event)


def tokens(name: str) -> list[str]:
    return [t for t in _SPLIT.split(name.upper()) if t]


def tournament_language(source_id: str, event_names: Iterable[str]) -> str:
    """'en' or the source's own language, from the codes the tournament's events use. A German
    or Flemish tournament written in English codes (MS A, XD A) is read as English."""
    if source_id not in ("tournamentsoftware_dbv", "tournamentsoftware_obv",
                         "tournamentsoftware_badvla"):  # fmt: skip
        return "source"
    seen = {t for n in event_names for t in tokens(n)[:2]}
    return "en" if seen & _ENGLISH and not seen & _GERMAN else "source"


@dataclass(frozen=True)
class Classified:
    discipline: str | None
    category: str  # "adult", "junior" or "para"


def classify(source_id: str, name: str, language: str = "source") -> Classified:
    table = _EN if language == "en" else _BY_SOURCE.get(source_id, _EN)
    found: set[tuple[str, bool]] = set()
    for t in tokens(name):
        if t in table:
            found.add(table[t])
        elif (m := _SUFFIX.match(t)) and m.group(1) in table:
            found.add(table[m.group(1)])
        elif (table is _EN or source_id == "tournamentsoftware_ba") and (
            g := _GRADE_PREFIX.match(t)
        ):
            found.add(_EN[g.group(1)])
    for pattern, disc, junior in _PHRASES:
        if re.search(rf"\b{pattern}\b", name, re.IGNORECASE):
            found.add((disc, junior))
    disciplines = {d for d, _ in found}
    discipline = disciplines.pop() if len(disciplines) == 1 else None
    words = " ".join(tokens(name))  # "_" and "-" separate words here ("SM_Sub17B")
    if _PARA.search(words):
        category = "para"
    elif any(j for _, j in found) or _JUNIOR.search(words):
        category = "junior"
    else:
        category = "adult"
    return Classified(discipline, category)


def fits(discipline: str | None, players_per_side: set[int]) -> bool:
    """A singles code on a doubles draw (or the reverse) is a misreading, not a fact."""
    if discipline is None or not players_per_side:
        return True
    return players_per_side == ({1} if discipline[1] == "S" else {2})


_NO_ENGLISH_FALLBACK = {
    "tournamentsoftware_dbv", "tournamentsoftware_obv", "tournamentsoftware_badvla",
    "tournamentsoftware_cbbd",
}  # fmt: skip


def discipline(source_id: str, name: str, language: str = "source") -> Classified:
    """`classify`, then the word-based reading of the name, which applies English codes too and
    so is used in a German, Dutch or Portuguese source only when the name holds no such code."""
    from scout.ingest.tournamentsoftware import discipline_of

    c = classify(source_id, name, language)
    # English words ("Men's Singles") read the same everywhere; English codes (GD, MD) do not
    english_codes = any(t in _EN for t in tokens(name))
    if c.discipline is None and (
        language == "en" or source_id not in _NO_ENGLISH_FALLBACK or not english_codes
    ):
        return Classified(discipline_of(name), c.category)
    return c


def reclassify(
    session: Session, tournament_ids: Iterable[int] | None = None, *, dry_run: bool = False
) -> Counter[str]:
    """Re-read every Tournament Software event's discipline and category in the context of its
    tournament. Counts changes as "<source> <old>-><new>" (events and their matches)."""
    from scout.models import Event, Match, MatchSide, MatchSidePlayer, Tournament

    q = (
        select(Event, Tournament.source_id)
        .join(Tournament, Tournament.id == Event.tournament_id)
        .where(Tournament.source_id.like("tournamentsoftware%"))
    )
    if tournament_ids is not None:
        q = q.where(Event.tournament_id.in_(list(tournament_ids)))
    events = session.execute(q).all()
    ids = [e.id for e, _ in events]
    per_side = (
        select(Match.event_id, func.count(MatchSidePlayer.position).label("n"))
        .join(MatchSide, MatchSide.match_id == Match.id)
        .join(MatchSidePlayer, MatchSidePlayer.match_side_id == MatchSide.id)
        .where(Match.event_id.in_(ids))
        .group_by(Match.event_id, MatchSide.id)
        .subquery()
    )
    shapes: defaultdict[int, set[int]] = defaultdict(set)
    for event_id, n in session.execute(select(per_side.c.event_id, per_side.c.n).distinct()):
        shapes[event_id].add(n)
    matches = dict(
        session.execute(
            select(Match.event_id, func.count())
            .where(Match.event_id.in_(ids))
            .group_by(Match.event_id)
        ).all()
    )
    names: defaultdict[int, list[str]] = defaultdict(list)
    for e, _ in events:
        names[e.tournament_id].append(e.name)
    counts: Counter[str] = Counter()
    for e, source in events:
        language = tournament_language(source, names[e.tournament_id])
        c = discipline(source, e.name, language)
        new = c.discipline
        if not fits(new, shapes[e.id]):
            counts["shape_conflict_left_unclassified"] += 1
            new = None
        if new != e.discipline:
            counts[f"events {source} {e.discipline}->{new}"] += 1
            counts[f"matches {source} {e.discipline}->{new}"] += matches.get(e.id, 0)
            if not dry_run:
                e.discipline = new
        if c.category != e.category and not dry_run:
            e.category = c.category
    if not dry_run:
        session.flush()
    return counts
