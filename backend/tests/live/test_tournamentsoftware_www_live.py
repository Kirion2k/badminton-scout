"""Live: www.tournamentsoftware.com behind its consent wall (ADR-0008 §6). Explicit only.

About 3 requests: minimal consent when the stored one is missing or old, then one read.
"""

import json

import pytest

from scout.budget import LedgerBudget
from scout.db import get_engine
from scout.ingest.api_anything import DEFAULT_HOME, local_runtime

pytestmark = pytest.mark.live


def test_consent_then_read_without_the_wall() -> None:
    budget = LedgerBudget(get_engine())
    with local_runtime(sites=["tournamentsoftware-www"], budget=budget) as client:
        record = json.loads((DEFAULT_HOME / "consent" / "tournamentsoftware-www.json").read_text())
        assert record["purposes"] == "1"  # basic functionality only
        budget.charge("tournamentsoftware", 1, purpose="live_test", note="www tournamentSearch")
        answer = client.call(
            "tournamentsoftware-www", "tournamentSearch", {"tab": "Recent", "page": 1}, max_tier=1
        )
    assert answer["ok"] is True and answer["tier"] == 1
    assert len(answer["data"]) > 0 and all("tournament?id=" in r["href"] for r in answer["data"])
