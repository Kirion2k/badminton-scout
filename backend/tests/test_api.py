from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine

from scout.db import get_engine
from scout.main import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_health_needs_no_database(client: httpx.AsyncClient) -> None:
    # no engine override: /health must not touch the database at all
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.db
async def test_ready_when_database_answers(
    app: FastAPI, client: httpx.AsyncClient, engine: Engine
) -> None:
    app.dependency_overrides[get_engine] = lambda: engine
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


async def test_not_ready_when_database_unreachable(app: FastAPI, client: httpx.AsyncClient) -> None:
    dead = create_engine(
        "postgresql+psycopg://nobody:secret-pw@127.0.0.1:1/none",
        connect_args={"connect_timeout": 1},
    )
    app.dependency_overrides[get_engine] = lambda: dead
    response = await client.get("/ready")
    dead.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}
    assert "secret-pw" not in response.text


async def test_product_endpoints_live_under_v1(client: httpx.AsyncClient) -> None:
    paths = set((await client.get("/openapi.json")).json()["paths"])
    assert {"/health", "/ready"} <= paths
    assert all(p.startswith("/v1/") for p in paths - {"/health", "/ready"})
