"""Every federation portal runs the ba. operations on its own host: its site spec must be the ba.
spec with only the host, name and federation changed.

Regenerate after editing the ba. spec or the portal table: `python -m tests.test_portal_specs`.
"""

import json
from pathlib import Path

import pytest

from scout.sources import TS_COOKIE_WALL_PORTALS, TS_FEDERATION_PORTALS

SITES = Path(__file__).resolve().parents[2] / "tools" / "api-anything" / "sites"


def expected(key: str) -> str:
    host, federation = TS_FEDERATION_PORTALS[key]
    text = (SITES / "tournamentsoftware-ba.json").read_text()
    text = text.replace("ba.tournamentsoftware.com", host)
    text = text.replace("Badminton Australia", federation)
    spec = json.loads(text)
    spec["name"] = f"tournamentsoftware-{key}"
    if key in TS_COOKIE_WALL_PORTALS:
        spec["loginCookies"] = ["st"]  # the consent cookie, imported once: no login probe
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("key", sorted(TS_FEDERATION_PORTALS))
def test_portal_spec_is_the_ba_spec_on_its_host(key: str) -> None:
    path = SITES / f"tournamentsoftware-{key}.json"
    assert path.exists() and path.read_text() == expected(key), (
        f"{path.name} is missing or stale: run `python -m tests.test_portal_specs` in backend/"
    )


if __name__ == "__main__":
    for key in TS_FEDERATION_PORTALS:
        (SITES / f"tournamentsoftware-{key}.json").write_text(expected(key))
