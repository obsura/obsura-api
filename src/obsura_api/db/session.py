"""Database engine and session helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from obsura_api.core.settings import Settings
from obsura_api.db.base import Base


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


def get_expected_table_names() -> set[str]:
    """Return the set of table names required by the current model metadata."""

    load_model_metadata()
    return set(Base.metadata.tables)


def get_missing_table_names(engine: Engine) -> list[str]:
    """Return required table names that are missing from the connected database."""

    expected_tables = get_expected_table_names()
    existing_tables = set(inspect(engine).get_table_names())
    return sorted(expected_tables - existing_tables)


def initialize_database(engine: Engine) -> None:
    """Create schema objects for local execution and tests."""

    load_model_metadata()
    Base.metadata.create_all(bind=engine)


def verify_database_connection(engine: Engine) -> None:
    """Fail fast if the configured database cannot accept a connection."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def ensure_database_schema(engine: Engine, *, auto_create: bool) -> list[str]:
    """Ensure the connected database has the required application tables."""

    missing_tables = get_missing_table_names(engine)
    if not missing_tables:
        return []

    if auto_create:
        initialize_database(engine)
        remaining_tables = get_missing_table_names(engine)
        if not remaining_tables:
            return missing_tables
        missing_tables = remaining_tables

    missing_table_list = ", ".join(missing_tables)
    raise RuntimeError(
        "Database schema is not initialized. Missing tables: "
        f"{missing_table_list}. Run the schema initialization step or enable "
        "OBSURA_AUTO_CREATE_SCHEMA for startup bootstrap.",
    )
