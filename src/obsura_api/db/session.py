"""Database engine and session helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
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


def initialize_database(engine: Engine) -> None:
    """Create schema objects for local execution and tests."""

    Base.metadata.create_all(bind=engine)
