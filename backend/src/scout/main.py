from fastapi import FastAPI

from scout.api import ops
from scout.api_v1 import router as v1


def create_app() -> FastAPI:
    app = FastAPI(title="Badminton Scout API", version="0.1.0")
    app.include_router(ops)
    app.include_router(v1)
    return app


app = create_app()
