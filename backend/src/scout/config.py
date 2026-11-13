from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/scout/config.py -> repository root. Missing file is ignored (e.g. when deployed).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCOUT_", env_file=_ENV_FILE, extra="ignore")

    # Required, no default: a forgotten SCOUT_ENV must not fall back to the least restrictive
    # environment. Any deployed instance, private or public, runs as "production" (ADR-0002).
    env: Environment
    # Required, no default: a missing URL must fail at startup, not fall back to some database.
    database_url: PostgresDsn


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # database_url comes from the environment
