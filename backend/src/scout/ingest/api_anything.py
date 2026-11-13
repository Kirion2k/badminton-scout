"""Running the pinned, local-only API Anything server (ADR-0007)."""

import os
import shutil
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

import api_anything

from scout.budget import Budget
from scout.ingest.consent import consent_is_current, establish_consent
from scout.ingest.provider import RuntimeUnavailable
from scout.sources import TS_COOKIE_WALL_PORTALS, TS_FEDERATION_PORTALS

# backend/src/scout/ingest/api_anything.py -> repository root
REPO = Path(__file__).resolve().parents[4]
DEFAULT_BINARY = REPO / "tools" / "api-anything" / "node_modules" / ".bin" / "api-anything"
DEFAULT_HOME = REPO / ".tools" / "api-anything-home"
# reviewed, exported operation specs (docs/api-anything.md step 7), installed on every start
SPECS_DIR = REPO / "tools" / "api-anything" / "sites"
# sites behind a cookie-consent wall: site -> (source, base URL). Minimal consent, ADR-0008 §6
CONSENT_SITES = {
    "tournamentsoftware-www": ("tournamentsoftware", "https://www.tournamentsoftware.com"),
    **{
        f"tournamentsoftware-{key}": (f"tournamentsoftware_{key}", f"https://{host}")
        for key, (host, _) in TS_FEDERATION_PORTALS.items()
        if key in TS_COOKIE_WALL_PORTALS
    },
}
# api_anything.Server merges os.environ into the child; everything else is blanked so the runtime
# never sees our settings, cloud credentials, tokens or API Anything overrides.
_CHILD_ENV_KEEP = frozenset({"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG", "TZ"})


@contextmanager
def local_runtime(
    *,
    binary: Path = DEFAULT_BINARY,
    home: Path = DEFAULT_HOME,
    specs: Path = SPECS_DIR,
    sites: Sequence[str] | None = None,
    timeout_s: float = 30,
    budget: Budget | None = None,
) -> Generator[api_anything.Client]:
    """Start `api-anything serve` on loopback and stop it on exit.

    Learning, writes and catalog access are all off: operations are learned only in the explicit
    development workflow (docs/api-anything.md), never by a running service.
    """
    if not binary.exists():
        raise RuntimeUnavailable(f"{binary} not found: run `make api-anything-install`")
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    installed = home / "sites"
    installed.mkdir(exist_ok=True, mode=0o700)
    for spec in specs.glob("*.json"):
        shutil.copyfile(spec, installed / spec.name)  # the repo's reviewed copy always wins
    overrides = {
        "API_ANYTHING_HOME": str(home),
        "API_ANYTHING_LOCAL_ONLY": "1",
    }
    for site in sites or ():
        if site in CONSENT_SITES and not consent_is_current(home, site):
            if budget is None:  # consent sends requests: they belong on the shared ledger
                raise RuntimeUnavailable(f"{site} needs consent: pass the shared budget")
            source_id, base_url = CONSENT_SITES[site]
            establish_consent(
                site=site, base_url=base_url, binary=binary, home=home, source_id=source_id,
                env={**{k: v for k, v in os.environ.items() if k in _CHILD_ENV_KEEP}, **overrides},
                budget=budget,
            )  # fmt: skip
    env = {**{name: "" for name in os.environ if name not in _CHILD_ENV_KEEP}, **overrides}
    try:
        client = api_anything.Client.start(
            timeout=timeout_s,
            command=[str(binary)],
            host="127.0.0.1",
            no_learn=True,
            sites=sites,
            env=env,
            startup_timeout=60,
        )
    except api_anything.ApiAnythingError as e:
        raise RuntimeUnavailable(f"API Anything failed to start: {e}") from None
    try:
        yield client
    finally:
        client.close()
