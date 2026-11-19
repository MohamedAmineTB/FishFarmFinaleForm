"""Alembic environment: the database URL comes from the app settings."""

from sqlalchemy import create_engine

from alembic import context
from app.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
