from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from scout.config import get_settings
from scout.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Tests pass their own database URL; everything else uses the configured one.
url = config.attributes.get("database_url") or str(get_settings().database_url)

with create_engine(url, poolclass=NullPool).connect() as connection:
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_server_default=True
    )
    with context.begin_transaction():
        context.run_migrations()
