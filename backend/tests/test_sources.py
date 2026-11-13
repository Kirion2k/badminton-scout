from types import MappingProxyType

import pytest

from scout import sources
from scout.cli import main
from scout.sources import (
    SourceNotPermitted,
    SourceRights,
    Use,
    can_serve,
    is_permitted,
    require_permitted,
)


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sources,
        "SOURCES",
        MappingProxyType(
            {
                "synthetic": sources.SOURCES["synthetic"],
                "unlicensed": SourceRights(frozenset(), "no licence found"),
                "store_only": SourceRights(
                    frozenset({Use.LOCAL_RESEARCH, Use.STORE}), "test grant"
                ),
            }
        ),
    )


@pytest.mark.parametrize("use", list(Use))
def test_unknown_source_is_denied_every_use(use: Use) -> None:
    assert not is_permitted("bwf_match_data", use)


@pytest.mark.parametrize("use", list(Use))
def test_synthetic_is_granted_every_use(use: Use) -> None:
    assert is_permitted("synthetic", use)


@pytest.mark.usefixtures("registry")
@pytest.mark.parametrize("use", list(Use))
def test_listed_source_without_grants_is_denied(use: Use) -> None:
    assert not is_permitted("unlicensed", use)


@pytest.mark.usefixtures("registry")
def test_production_needs_hosting_and_redistribution() -> None:
    assert can_serve("store_only", "development")
    assert not can_serve("store_only", "production")
    assert not can_serve("unlicensed", "development")
    assert can_serve("synthetic", "production")


def test_unassessed_environment_fails_closed() -> None:
    assert not can_serve("synthetic", "staging")  # pyright: ignore[reportArgumentType]


def test_require_permitted_raises() -> None:
    require_permitted("synthetic", Use.HOSTED)
    with pytest.raises(SourceNotPermitted, match="bwf_match_data"):
        require_permitted("bwf_match_data", Use.STORE)


def test_grant_without_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="evidence"):
        SourceRights(frozenset({Use.STORE}), "  ")


def test_registry_cannot_be_mutated() -> None:
    with pytest.raises(TypeError):
        sources.SOURCES["x"] = SourceRights(frozenset(Use), "nope")  # type: ignore[index]


def test_cli_lists_sources(capsys: pytest.CaptureFixture[str]) -> None:
    main(["sources"])
    assert "synthetic: local_research, store" in capsys.readouterr().out
