"""Alembic migration helpers and CLI for Obsura API."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from obsura_api.core.settings import Settings


ALEMBIC_SCRIPT_LOCATION = Path(__file__).resolve().parent / "alembic"


@dataclass(slots=True)
class SchemaState:
    """Observed migration state for the connected database."""

    current_revision: str | None
    expected_revision: str
    has_version_table: bool
    has_application_tables: bool

    @property
    def is_at_head(self) -> bool:
        return self.current_revision == self.expected_revision


def create_alembic_config(
    database_url: str,
    *,
    script_location: Path | None = None,
) -> Config:
    """Create an Alembic config object bound to the given database URL."""

    config = Config()
    config.set_main_option(
        "script_location",
        str((script_location or ALEMBIC_SCRIPT_LOCATION).resolve()),
    )
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url"] = database_url
    return config


def get_head_revision(database_url: str) -> str:
    """Return the single expected Alembic head revision for the app."""

    script = ScriptDirectory.from_config(create_alembic_config(database_url))
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            "Obsura API expects exactly one Alembic head revision. "
            f"Found: {', '.join(heads) or '(none)'}",
        )
    return heads[0]


def get_current_revision(engine: Engine) -> str | None:
    """Return the current Alembic revision recorded in the database."""

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def get_schema_state(engine: Engine, database_url: str) -> SchemaState:
    """Inspect the connected database and compare it to the Alembic head."""

    table_names = set(inspect(engine).get_table_names())
    return SchemaState(
        current_revision=get_current_revision(engine),
        expected_revision=get_head_revision(database_url),
        has_version_table="alembic_version" in table_names,
        has_application_tables=bool(table_names - {"alembic_version"}),
    )


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Apply Alembic migrations to the target revision."""

    command.upgrade(create_alembic_config(database_url), revision)


def describe_schema_mismatch(state: SchemaState) -> str:
    """Build an operator-facing schema state error message."""

    if state.current_revision is None and not state.has_application_tables:
        return (
            "Database schema is not initialized. Apply Alembic migrations with "
            "`obsura-api-migrate upgrade head` or `alembic -c alembic.ini upgrade head`."
        )
    if state.current_revision is None and state.has_application_tables:
        return (
            "Database contains Obsura tables but is not stamped with an Alembic revision. "
            "Run `obsura-api-migrate upgrade head` or `alembic -c alembic.ini upgrade head` "
            "to reconcile and stamp the schema."
        )
    return (
        "Database schema revision is not at the expected application head. "
        f"Current revision: {state.current_revision}. Expected revision: {state.expected_revision}. "
        "Apply Alembic migrations before starting the API."
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for migration operations."""

    parser = argparse.ArgumentParser(description="Obsura API Alembic migration helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade_parser = subparsers.add_parser("upgrade", help="Apply migrations to a target revision.")
    upgrade_parser.add_argument("revision", nargs="?", default="head")

    subparsers.add_parser("current", help="Print the current database revision.")
    subparsers.add_parser("check", help="Exit non-zero if the database is not at head.")

    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for database migration operations."""

    from obsura_api.db.session import create_engine_from_settings

    args = parse_args()
    settings = Settings(auto_create_schema=False)

    if args.command == "upgrade":
        upgrade_database(settings.database_url, args.revision)
        return

    engine = create_engine_from_settings(settings)
    state = get_schema_state(engine, settings.database_url)

    if args.command == "current":
        print(state.current_revision or "(none)")
        return

    if state.is_at_head:
        print(f"Database revision is at head: {state.expected_revision}")
        return

    print(describe_schema_mismatch(state))
    raise SystemExit(1)


if __name__ == "__main__":
    main()
