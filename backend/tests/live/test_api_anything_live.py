"""Live smoke test of the real API Anything runtime against the approved HN search operation.

Excluded from `make check` and CI. Run explicitly with `make api-anything-smoke`.
It reads public HN search results, stores nothing, and never touches a badminton site.
"""

import logging
from collections.abc import Iterator

import api_anything
import pytest

from scout.budget import LedgerBudget
from scout.db import get_engine
from scout.ingest.api_anything import local_runtime
from scout.ingest.operations import HackerNewsHit
from scout.ingest.provider import ApiAnythingProvider, OperationFailed, RuntimeUnavailable

pytestmark = pytest.mark.live


def _ledger() -> LedgerBudget:
    """Live tests spend the same shared budget as ingestion (ADR-0008)."""
    return LedgerBudget(get_engine())


@pytest.fixture(scope="module")
def client() -> Iterator[api_anything.Client]:
    with local_runtime(sites=["hacker-news"]) as client:
        yield client
    server = client.server
    assert server is None  # close() released it


def test_runtime_is_healthy_and_local(client: api_anything.Client) -> None:
    health = client.health()
    assert health["ok"] is True
    assert health["version"] == "0.4.0"
    assert client.base_url.startswith("http://127.0.0.1:")


def test_approved_operation_is_discoverable(client: api_anything.Client) -> None:
    ops = {o["name"]: o for o in client.operations("hacker-news")["operations"]}
    assert "search" in ops
    assert "query" in ops["search"]["inputSchema"]["properties"]


def test_fetch_validates_real_answer(
    client: api_anything.Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    provider = ApiAnythingProvider(client, budget=_ledger(), purpose="live_test")
    result = provider.fetch("hacker_news.search", {"query": "sqlite"})
    assert result.tier == 1
    assert 0 < len(result.items) <= 30
    assert all(isinstance(i, HackerNewsHit) for i in result.items)
    print(
        f"\nhacker_news.search: {len(result.items)} items, tier {result.tier}, "
        f"{result.elapsed_ms} ms, {result.attempts} attempt(s), fields "
        f"{sorted(HackerNewsHit.model_fields)}"
    )
    token = client._auth_token()  # pyright: ignore[reportPrivateUsage]
    assert token and token not in caplog.text


def test_invalid_input_fails_as_input_without_retry(client: api_anything.Client) -> None:
    provider = ApiAnythingProvider(client, budget=_ledger(), purpose="live_test")
    with pytest.raises(OperationFailed) as e:
        provider.fetch("hacker_news.search", {"query": "sqlite", "type": "not-a-type"})
    assert e.value.klass == "input"


def test_unreachable_runtime_is_reported() -> None:
    dead = api_anything.Client("http://127.0.0.1:1", token="unused", timeout=2)  # noqa: S106
    with pytest.raises(RuntimeUnavailable):
        provider = ApiAnythingProvider(dead, budget=_ledger(), purpose="live_test")
        provider.fetch("hacker_news.search", {"query": "sqlite"})
