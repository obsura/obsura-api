"""Database engine and session helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from obsura_api.core.settings import Settings
from obsura_api.db.migrations import (
    SchemaState,
    describe_schema_mismatch,
    get_schema_state,
    upgrade_database,
)


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create an engine that supports both local SQLite and production databases."""

    database_url = settings.database_url
    parsed_url = make_url(database_url)
    connect_args: dict[str, object] = {}

    if parsed_url.drivername.startswith("sqlite"):
        database_path = parsed_url.database
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False

    return create_engine(
        database_url,
        future=True,
        connect_args=connect_args,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the repository-wide SQLAlchemy session factory."""

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def load_model_metadata() -> None:
    """Import model modules so the declarative metadata registry is populated."""

    from obsura_api.db import models as _models  # noqa: F401


def upgrade_database_from_settings(settings: Settings, revision: str = "head") -> None:
    """Apply Alembic migrations for the configured database."""

    upgrade_database(settings.database_url, revision)


def verify_database_connection(engine: Engine) -> None:
    """Fail fast if the configured database cannot accept a connection."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def ensure_database_schema(engine: Engine, *, settings: Settings) -> SchemaState:
    """Ensure the connected database is at the expected Alembic revision."""

    schema_state = get_schema_state(engine, settings.database_url)
    if schema_state.is_at_head:
        return schema_state

    if settings.auto_create_schema:
        upgrade_database_from_settings(settings)
        schema_state = get_schema_state(engine, settings.database_url)
        if schema_state.is_at_head:
            return schema_state

    raise RuntimeError(describe_schema_mismatch(schema_state))
