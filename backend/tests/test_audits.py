"""Data-quality audits on the synthetic fixture (counts only, never names)."""

import pytest
from sqlalchemy.orm import Session

from scout.ratings.audit import gender_consistency, side_order
from tests.test_api_v1 import data, player_id  # noqa: F401  # pyright: ignore[reportUnusedImport]

pytestmark = pytest.mark.db


def test_side_order_counts_every_completed_federation_singles_match(data: Session) -> None:  # noqa: F811
    from sqlalchemy import update

    from scout.models import Tournament

    data.execute(update(Tournament).values(source_id="tournamentsoftware_ba"))
    out = side_order(data.connection())
    by_seed = out["by_seed"]
    assert sum(v["matches"] for v in by_seed.values()) == sum(
        v["matches"] for v in out["by_stage"].values()
    )
    assert all(0 <= v["side_1_win_rate"] <= 1 for v in by_seed.values())


def test_gender_consistency_reads_doubles_against_singles(data: Session) -> None:  # noqa: F811
    out = gender_consistency(data.connection())
    for counts in out.values():
        assert set(counts) <= {"fits", "contradicts", "unknown"}
    assert any(k.endswith((" MD", " WD", " XD")) for k in out)
