"""What may leave the system (ADR-0010, superseding ADR-0009's default).

`is_adult_event` is an allowlist: an event is adult only when every word of its name is a known
adult-event word. Junior events hold minors' data and para classes health data; any unknown word
(an age band, a para class, a youth label in any language) makes an event restricted.

Whether restricted events are served is the owner's decision, recorded in ADR-0010:
`PUBLISH_RESTRICTED_EVENTS`. Turning it off and running `scout privacy reclassify` hides them again.
"""

import hashlib
import hmac
import re
import urllib.parse

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


# One global rule for identifiers (ADR-0010 follow-up): a member id that may be a national identity
# number is never stored in clear: Brazil's CPF and Malaysia's NRIC were seen (shapes below). A
# keyed hash keeps the same person on the same key; without a key the id is dropped (and counted).
_NATIONAL_ID = re.compile(r"(?<![0-9A-Za-z])\d[\d.\- ]{7,16}\d(?![0-9A-Za-z])")
_INVISIBLE = re.compile(r"[\s\u00a0\u200b-\u200d\u2060\ufeff]+")


def national_id(value: str) -> str | None:
    """The digits of a possible national identity number in `value` (encoded or not), or None."""
    decoded = _INVISIBLE.sub(" ", urllib.parse.unquote_plus(value)).strip()
    found = _NATIONAL_ID.search(decoded)
    if not found:
        return None
    digits = re.sub(r"\D", "", found.group())
    # the formats seen: CPF (11 digits, written ddd.ddd.ddd-dd or bare) and NRIC (12 digits,
    # dddddd-dd-dddd or bare). Other long member ids are ordinary association numbers.
    shapes = r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}|\d{6}-\d{2}-\d{4}|\d{12}"
    shaped = re.fullmatch(shapes, found.group())
    return digits if shaped and found.group().strip() == decoded else None


def minimise_identifier(value: str, key: str | None) -> str | None:
    digits = national_id(value)
    if digits is None:
        return value
    if not key:
        return None
    # 11 digits hash in the CPF's written form, as the first stored tokens were (2026-11-13)
    canonical = digits
    if len(digits) == 11:
        canonical = f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return "h-" + hmac.new(key.encode(), canonical.encode(), hashlib.sha256).hexdigest()[:24]


_MEMBER_PARAM = re.compile(r"([?&])(T\dP\dMemberID)=([^&#]*)")


def minimise_h2h(url: str | None, key: str | None) -> str | None:
    """The head-to-head link with national-identity member ids replaced in place (or removed).
    Anything else is returned byte for byte: re-encoding would change keys and revisions."""
    if not url or "MemberID=" not in url:
        return url

    def one(m: re.Match[str]) -> str:
        minimal = minimise_identifier(m.group(3), key)
        if minimal == m.group(3):
            return m.group(0)
        return "" if minimal is None else f"{m.group(1)}{m.group(2)}={minimal}"

    out = _MEMBER_PARAM.sub(one, url)
    return out if "?" in out or "?" not in url else out.replace("&", "?", 1)


def key_fingerprint(key: str) -> str:
    """Identifies the identifier key without revealing it: stored to catch a changed key."""
    digest = hmac.new(key.encode(), b"badminton-scout identifier key", hashlib.sha256)
    return digest.hexdigest()[:16]
