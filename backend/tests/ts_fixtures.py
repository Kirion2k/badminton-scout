"""Synthetic Tournament Software rows shaped like real MatchesInDay output. Invented names/ids."""

from typing import Any

TOURNAMENT = "aaaaaaaa-1111-2222-3333-444444444444"
ORG = "bbbbbbbb-0000-0000-0000-000000000000"
DAY = "20260105"


def row(
    *,
    draw: int = 7,
    event: str = "MS C - Group A",
    round_: str = "Round 1",
    side1: tuple[tuple[str, str, str | None], ...] = (("101", "Alex TESTER", "QA1001"),),
    side2: tuple[tuple[str, str, str | None], ...] = (("102", "Sam EXAMPLE", "QA1002"),),
    winner: int | None = 1,
    points: tuple[int, ...] = (21, 15, 21, 18),
    message: str | None = None,
    info: str | None = "Duration: 31m | Main Location - 04",
) -> dict[str, Any]:
    """One row as the matchesInDay operation returns it (player tuples: id, name, member id)."""
    members = [
        f"T{t}P{p}MemberID={m}"
        for t, side in ((1, side1), (2, side2))
        for p, (_, _, m) in enumerate(side, start=1)
        if m
    ]
    out: dict[str, Any] = {
        "event": event,
        "drawHref": f"https://ba.tournamentsoftware.com/sport/draw.aspx?id={TOURNAMENT}&draw={draw}",
        "round": round_,
        "info": info,
        "side1Ids": [p[0] for p in side1],
        "side1Names": [p[1] for p in side1],
        "side2Ids": [p[0] for p in side2],
        "side2Names": [p[1] for p in side2],
        "rowClasses": [
            "match__row has-won" if winner == 1 else "match__row ",
            "match__row has-won" if winner == 2 else "match__row ",
        ],
        "points": [str(p) for p in points],
        "h2h": f"https://ba.tournamentsoftware.com/head-2-head?OrganizationCode={ORG}&"
        + "&".join(members),
    }
    if message:
        out["message"] = message
    return out


DOUBLES = row(
    draw=9,
    event="XD Open",
    side1=(("201", "Kim SAMPLE", "QA2001"), ("202", "Lee PLACEHOLDER", "QA2002")),
    side2=(("203", "Pat DUMMY", "QA2003"), ("204", "Chris MOCK", "QA2004")),
    winner=2,
    points=(19, 21, 21, 17, 15, 21),
    info="Duration: 1h 5m | Main Location - 02",
)
WALKOVER = row(draw=7, round_="Round 2", points=(), message="Walkover", info="Hall B")
ONE_GAME_TO_30 = row(draw=8, event="WS D", points=(30, 24))


def listing(
    guid: str = TOURNAMENT.upper(),
    name: str = "Synthetic Open 2026",
    subheading: str = "Synthetic Badminton Association | Testville",
    dates: tuple[str, ...] = ("2026-01-05 00:00", "2026-01-06 23:59"),
) -> dict[str, Any]:
    """One row as the tournamentSearch operation returns it."""
    return {
        "name": f"  {name} ",
        "href": f"https://ba.tournamentsoftware.com/sport/tournament?id={guid}",
        "subheading": subheading,
        "dates": list(dates),
    }
