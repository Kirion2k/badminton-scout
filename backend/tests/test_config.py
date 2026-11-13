import pytest
from pydantic import ValidationError

from scout.config import Settings

URL = "postgresql+psycopg://u:p@localhost:5433/scout"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SCOUT_ENV", "SCOUT_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def settings(**values: str) -> Settings:
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def test_database_url_is_required() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        settings(env="development")


def test_environment_is_required() -> None:
    # no silent fallback to "development" in a deployment that forgot SCOUT_ENV
    with pytest.raises(ValidationError, match="env"):
        settings(database_url=URL)


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUT_DATABASE_URL", URL)
    monkeypatch.setenv("SCOUT_ENV", "production")
    s = settings()
    assert s.env == "production"
    assert s.database_url.hosts()[0]["port"] == 5433


@pytest.mark.parametrize("env", ["staging", "prod", ""])
def test_unknown_environment_is_rejected(env: str) -> None:
    with pytest.raises(ValidationError):
        settings(database_url=URL, env=env)


def test_non_postgres_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        settings(env="development", database_url="mysql://u:p@localhost/scout")
