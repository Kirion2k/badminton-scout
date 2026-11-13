from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from scout.db import get_engine

ops = APIRouter(tags=["ops"])


class Health(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["ok", "unreachable"]


@ops.get("/health")
def health() -> Health:
    """Liveness: the process is up. Touches no dependency."""
    return Health(status="ok")


@ops.get("/ready", responses={503: {"model": Readiness}})
def ready(response: Response, engine: Annotated[Engine, Depends(get_engine)]) -> Readiness:
    """Readiness: dependencies answer. Errors are not echoed, so credentials can't leak."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="unavailable", database="unreachable")
    return Readiness(status="ready", database="ok")
