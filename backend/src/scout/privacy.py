"""What may leave the system (ADR-0010, superseding ADR-0009's default).

`is_adult_event` is an allowlist: an event is adult only when every word of its name is a known
adult-event word. Junior events hold minors' data and para classes health data; any unknown word
(an age band, a para class, a youth label in any language) makes an event restricted.

Whether restricted events are served is the owner's decision, recorded in ADR-0010:
`PUBLISH_RESTRICTED_EVENTS`. Turning it off and running `scout privacy reclassify` hides them again.
"""

import re

# ADR-0010 (2026-11-13): the owner decided to publish junior and para events too
PUBLISH_RESTRICTED_EVENTS = True

_ADULT_PREFIXES = {"ms", "ws", "md", "wd", "xd"}
# Other spellings of the five disciplines, mapped to the standard prefix: Vietnamese, and the
# glued English with a typographic apostrophe and hyphen ("Men's Singles-2" written as one
# word). Only the discipline words are replaced, so an age band after them (Đơn Nam U13) still
# keeps the event private.
_ALIASES = [
    (r"đôi\s+nam\s+nữ", "XD"),
    (r"đôi\s+nam", "MD"),
    (r"đôi\s+nữ", "WD"),
    (r"đơn\s+nam", "MS"),
    (r"đơn\s+nữ", "WS"),
    (r"men['\u2019]?s\s*singles", "MS"),
    (r"women['\u2019]?s\s*singles", "WS"),
    (r"men['\u2019]?s\s*doubles", "MD"),
    (r"women['\u2019]?s\s*doubles", "WD"),
    (r"mixed\s*doubles", "XD"),
]
_DAY = r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*"
_DATE = r"\d{1,2}/\d{1,2}(/\d{2,4})?"
_ADULT_WORD = re.compile(
    r"^("
    r"[a-e]|[a-e]/[a-e]s?|&|open|reserve|grade|combined|mixed|division|div|\d"  # grades, divisions
    r"|n[1-7]"  # Vietnamese club skill levels (trình độ N1-N7), adult
    r"|[3-9]\d\+?|plus"  # masters ages: 30 and over only
    rf"|{_DAY}|{_DATE}|{_DAY}{_DATE}"  # day labels, glued or not
    r"|please|see|conditions?|c"  # "Please see conditions", sometimes cut to "Please see c"
    r")$"
)


def canonical_event(name: str) -> str:
    """The name with a known alternative discipline spelling replaced by its prefix."""
    name = name.strip().replace("\u2010", "-").replace("\u2013", "-")
    for pattern, prefix in _ALIASES:
        replaced, n = re.subn(rf"^{pattern}(?=[\s\-]|$)", f"{prefix} ", name, flags=re.IGNORECASE)
        if n:
            return replaced.strip()
    return name


def is_redistributable_event(name: str, discipline: str | None) -> bool:
    """Whether an event's matches may be served (stored as `event.redistributable`)."""
    return PUBLISH_RESTRICTED_EVENTS or is_adult_event(name, discipline)


def is_adult_event(name: str, discipline: str | None) -> bool:
    """A recognisably adult event. Anything unclear counts as restricted."""
    if discipline is None:
        return False
    # draw sections ("- Group A", "- Position 1-8") are not part of the category
    name = re.sub(r"\s-\s*(Group|Position)\s+\S+$", "", canonical_event(name), flags=re.IGNORECASE)
    words = re.split(r"[\s(),\-]+", name.casefold())
    words = [w for w in words if w]
    if not words or words[0] not in _ADULT_PREFIXES:
        return False
    return all(_ADULT_WORD.match(w) for w in words[1:])
