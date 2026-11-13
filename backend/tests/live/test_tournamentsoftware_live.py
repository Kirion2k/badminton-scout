"""Live: the approved Tournament Software (Badminton Australia) operations against the real site.

Explicit only (`make api-anything-smoke`). About 3 requests, paced 5 s apart (ADR-0008).
Uses a completed tournament verified on 2026-11-12. A changed count means the source changed:
investigate before updating the expectation.
"""

from collections.abc import Iterator
from datetime import date

import pytest

from scout.budget import LedgerBudget
from scout.db import get_engine
from scout.ingest.api_anything import local_runtime
from scout.ingest.operations import TsMatchDay, TsMatchRow
from scout.ingest.provider import ApiAnythingProvider, OperationFailed
from scout.ingest.tournamentsoftware import NormalizedMatch, normalize

pytestmark = pytest.mark.live


def _ledger() -> LedgerBudget:
    """Live tests spend the same shared budget as ingestion (ADR-0008)."""
    return LedgerBudget(get_engine())


VIC_GRADED_3 = "325A6E18-4E5D-4D3F-BE3C-6CB62687ED9D"


@pytest.fixture(scope="module")
def provider() -> Iterator[ApiAnythingProvider]:
    with local_runtime(sites=["tournamentsoftware-ba"]) as client:
        yield ApiAnythingProvider(client, budget=_ledger(), purpose="live_test")


def test_match_days(provider: ApiAnythingProvider) -> None:
    result = provider.fetch("tournamentsoftware_ba.match_days", {"tournament": VIC_GRADED_3})
    assert [d.date for d in result.items if isinstance(d, TsMatchDay)] == ["20261010", "20261011"]
    assert result.tier == 1


def test_matches_in_day_is_complete_and_normalizes(provider: ApiAnythingProvider) -> None:
    result = provider.fetch(
        "tournamentsoftware_ba.matches_in_day", {"tournament": VIC_GRADED_3, "date": "20261011"}
    )
    rows = [i for i in result.items if isinstance(i, TsMatchRow)]
    # 101, not 35: the runtime cuts long answers and the provider must read the rest
    assert len(rows) == 101
    normalized = [normalize(r, date(2026, 10, 11)) for r in rows]
    assert all(isinstance(n, NormalizedMatch) for n in normalized)
    print(f"\nmatches_in_day: {len(rows)} rows, tier {result.tier}, {result.elapsed_ms} ms")


def test_unknown_tournament_fails_as_input(provider: ApiAnythingProvider) -> None:
    with pytest.raises(OperationFailed) as e:
        provider.fetch(
            "tournamentsoftware_ba.matches_in_day",
            {"tournament": "00000000-0000-0000-0000-000000000000", "date": "20261011"},
        )
    assert e.value.klass == "input"


def test_malformed_tournament_is_refused_before_sending(provider: ApiAnythingProvider) -> None:
    with pytest.raises(OperationFailed) as e:
        provider.fetch("tournamentsoftware_ba.match_days", {"tournament": "not-a-guid"})
    assert e.value.klass == "input"
