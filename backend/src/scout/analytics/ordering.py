"""Same-day order of matches from their round labels (ADR-0012). Pure: no I/O."""

import math
import re
from collections.abc import Callable, Iterable, Iterator
from datetime import date
from itertools import groupby

# Bands: qualification, then groups, then numbered rounds, then the sized main draw.
_QUAL, _GROUP, _NUMBERED, _MAIN = 0, 1000, 2000, 3000
_CONSOLATION = 5  # a consolation or placement round follows the main round of the same size
_NAMED = {
    "final": 2,
    "finale": 2,
    "semi final": 4,
    "semi finals": 4,
    "semifinal": 4,
    "semifinals": 4,
    "halve finale": 4,
    "sf": 4,
    "quarter final": 8,
    "quarter finals": 8,
    "quarterfinal": 8,
    "quarterfinals": 8,
    "kwartfinale": 8,
    "qf": 8,
}
_PREFIX = re.compile(r"^(?:q qual\.?|qualification|q)(?:\s+|$)", re.IGNORECASE)
_CONS = re.compile(r"^(?:consolation|verliezersronde)\s+", re.IGNORECASE)
_SIZED = re.compile(r"^(?:r|round of|ronde van)\s*(\d+)$", re.IGNORECASE)
_NUMBER = re.compile(r"^(?:round|ronde|r)\s*(\d+)$", re.IGNORECASE)
_PLACE = re.compile(r"^(\d+)(?:st|nd|rd|th)?\s*/\s*(\d+)(?:st|nd|rd|th)?(?:\s+place)?$")


def _sized(size: int) -> int:
    """Larger rounds first: R512 < R256 < … < Final."""
    return (20 - int(math.log2(size))) * 10 if size >= 2 and size & (size - 1) == 0 else -1


def round_rank(label: str | None) -> int | None:
    """An order key within one day, or None when the label says nothing usable."""
    if not label or not label.strip():
        return None
    text = " ".join(label.replace("-", " ").split()).lower()
    base, rest = _MAIN, text
    if q := _PREFIX.match(text):
        base, rest = _QUAL, text[q.end() :]
        if not rest:  # a bare "Q": qualification, round unknown
            return _QUAL
    bonus = 0
    if c := _CONS.match(rest):
        bonus, rest = _CONSOLATION, rest[c.end() :]
    if rest.startswith("group") or rest.startswith("pool") or rest.startswith("poule"):
        return _GROUP
    if place := _PLACE.match(rest.removeprefix("consolation ")):
        # "5th/8th place" decides places among 4 players: a semi-final-sized round
        size = int(place.group(2)) - int(place.group(1)) + 1
        size = 1 << max(1, (size - 1).bit_length())
        return base + _sized(size) + _CONSOLATION
    if rest in _NAMED:
        return base + _sized(_NAMED[rest]) + bonus
    sized = _SIZED.match(rest)
    # "R16" is a round of 16, but "R2" is the second round ("R<n>" is sized only above 8)
    if (
        sized
        and (int(sized.group(1)) > 8 or not re.match(r"r\s*\d", rest))
        and (rank := _sized(int(sized.group(1)))) >= 0
    ):
        return base + rank + bonus
    if numbered := _NUMBER.match(rest):
        # "Round 3" / "R3": the third round of its draw, whatever the draw's size
        return (_QUAL if base == _QUAL else _NUMBERED) + int(numbered.group(1)) * 10 + bonus
    return None


def batch_key(day: date, rank: int | None, *, by_round: bool = True) -> tuple[date, float]:
    """Matches with equal keys are predicted from the same state and applied together. An
    unlabelled match waits for the end of its day."""
    if not by_round:
        return (day, 0.0)
    return (day, math.inf if rank is None else float(rank))


def batches[T](items: Iterable[T], key: Callable[[T], tuple[date, float]]) -> Iterator[list[T]]:
    """Consecutive batches in order. Ties keep the input order (sorted() is stable)."""
    for _, group in groupby(sorted(items, key=key), key=key):
        yield list(group)
