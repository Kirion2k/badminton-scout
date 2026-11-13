from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from scout.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    cfg = Config(BACKEND / "alembic.ini")
    cfg.attributes["database_url"] = database_url
    return cfg


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """A fresh `<configured db>_test` database on the configured server, recreated per session."""
    settings = get_settings()
    url = make_url(str(settings.database_url))
    # this fixture drops a database: only ever on a local, non-production server
    if settings.env == "production" or url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.exit(
            f"refusing to drop/create test databases (env={settings.env}, host={url.host})",
            returncode=2,
        )
    test_url = url.set(database=f"{url.database}_test")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{test_url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    admin.dispose()
    return test_url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine(test_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(test_db_url), "head")
    engine = create_engine(test_db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test."""
    with engine.connect() as conn, conn.begin() as tx:
        yield Session(bind=conn, join_transaction_mode="create_savepoint")
        tx.rollback()
