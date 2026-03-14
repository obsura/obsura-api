from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from obsura_api import app as app_module
from obsura_api.core.settings import DEFAULT_DEVELOPMENT_DATABASE_URL, Settings, get_settings
from obsura_api.db.base import Base
from obsura_api.db.migrations import SchemaState, get_schema_state
from obsura_api.db import session as session_module


@pytest.fixture(autouse=True)
def clear_settings_env(monkeypatch) -> None:
    for key in (
        "DATABASE_URL",
        "OBSURA_DATABASE_URL",
        "OBSURA_ENV",
        "OBSURA_ENVIRONMENT",
        "OBSURA_AUTO_CREATE_SCHEMA",
        "OBSURA_CORS_ALLOWED_ORIGINS",
        "CORS_ALLOWED_ORIGINS",
        "OBSURA_ALLOWED_HOSTS",
        "ALLOWED_HOSTS",
        "OBSURA_CORS_ALLOW_CREDENTIALS",
        "CORS_ALLOW_CREDENTIALS",
        "OBSURA_OCR_BACKEND",
        "OBSURA_OCR_PROVIDER",
        "OBSURA_OCR_LANGUAGE",
        "OBSURA_TESSERACT_LANG",
        "OBSURA_PII_BACKEND",
        "OBSURA_PII_PROVIDER",
        "OBSURA_NLP_BACKEND",
        "OBSURA_PII_LANGUAGE",
        "OBSURA_PRESIDIO_LANGUAGE",
        "OBSURA_PRESIDIO_MODEL",
        "OBSURA_PII_MODEL",
        "OBSURA_PRESIDIO_SCORE_THRESHOLD",
        "OBSURA_PII_SCORE_THRESHOLD",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def test_reads_database_url_from_canonical_env(monkeypatch) -> None:
    database_url = "postgresql+psycopg://obsura:password@postgres:5432/obsura"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == database_url


@pytest.mark.parametrize(
    ("raw_database_url", "expected_database_url"),
    (
        (
            "postgresql://obsura:password@postgres:5432/obsura",
            "postgresql+psycopg://obsura:password@postgres:5432/obsura",
        ),
        (
            "postgres://obsura:password@postgres:5432/obsura",
            "postgresql+psycopg://obsura:password@postgres:5432/obsura",
        ),
        (
            "postgresql+psycopg2://obsura:password@postgres:5432/obsura",
            "postgresql+psycopg://obsura:password@postgres:5432/obsura",
        ),
    ),
)
def test_normalizes_supported_postgres_driver_aliases(
    monkeypatch,
    raw_database_url: str,
    expected_database_url: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", raw_database_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == expected_database_url


def test_reads_database_url_from_obsura_alias(monkeypatch) -> None:
    database_url = "postgresql+psycopg://obsura:password@postgres:5432/obsura"
    monkeypatch.setenv("OBSURA_DATABASE_URL", database_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == database_url


def test_production_rejects_missing_database_url(monkeypatch) -> None:
    monkeypatch.setenv("OBSURA_ENV", "production")

    with pytest.raises(ValidationError, match="Production environment requires DATABASE_URL"):
        Settings(_env_file=None)


def test_production_rejects_sqlite_database_url(monkeypatch) -> None:
    monkeypatch.setenv("OBSURA_ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/obsura.db")

    with pytest.raises(ValidationError, match="Production environment requires a PostgreSQL"):
        Settings(_env_file=None)


def test_production_rejects_automatic_schema_upgrade(monkeypatch) -> None:
    monkeypatch.setenv("OBSURA_ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://obsura:password@postgres:5432/obsura")
    monkeypatch.setenv("OBSURA_AUTO_CREATE_SCHEMA", "true")

    with pytest.raises(ValidationError, match="must not use OBSURA_AUTO_CREATE_SCHEMA=true"):
        Settings(_env_file=None)


def test_development_allows_sqlite_fallback() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == DEFAULT_DEVELOPMENT_DATABASE_URL


def test_default_cors_origins_allow_local_frontends() -> None:
    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    assert settings.cors_allow_credentials is True


def test_reads_pii_settings_from_aliases(monkeypatch) -> None:
    monkeypatch.setenv("OBSURA_NLP_BACKEND", "presidio")
    monkeypatch.setenv("OBSURA_PRESIDIO_LANGUAGE", "en")
    monkeypatch.setenv("OBSURA_PII_MODEL", "en_core_web_sm")
    monkeypatch.setenv("OBSURA_PII_SCORE_THRESHOLD", "0.55")

    settings = Settings(_env_file=None)

    assert settings.pii_backend == "presidio"
    assert settings.pii_language == "en"
    assert settings.presidio_model == "en_core_web_sm"
    assert settings.presidio_score_threshold == 0.55


def test_parses_comma_separated_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv(
        "OBSURA_CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000/, http://localhost:5173",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == (
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    )


def test_parses_comma_separated_allowed_hosts_alias(monkeypatch) -> None:
    monkeypatch.setenv(
        "ALLOWED_HOSTS",
        "https://obsura.one/, https://api.obsura.one",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == (
        "https://obsura.one",
        "https://api.obsura.one",
    )


def test_rejects_wildcard_cors_origin_when_credentials_enabled(monkeypatch) -> None:
    monkeypatch.setenv("OBSURA_CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("OBSURA_CORS_ALLOW_CREDENTIALS", "true")

    with pytest.raises(ValidationError, match="must not include '\\*'"):
        Settings(_env_file=None)


def test_engine_uses_resolved_database_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_engine(url, *, future: bool, connect_args: dict[str, object]):
        captured["url"] = url
        captured["future"] = future
        captured["connect_args"] = connect_args
        return object()

    monkeypatch.setattr(session_module, "create_engine", fake_create_engine)
    settings = Settings(
        database_url="postgresql+psycopg://obsura:password@postgres:5432/obsura",
        _env_file=None,
    )

    session_module.create_engine_from_settings(settings)

    assert captured["url"] == settings.database_url
    assert captured["future"] is True
    assert captured["connect_args"] == {}


def test_app_logs_sanitized_database_backend(monkeypatch, tmp_path: Path, caplog) -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://obsura:password@postgres:5432/obsura",
        storage_root=tmp_path / "storage",
        auto_create_schema=False,
        _env_file=None,
    )

    monkeypatch.setattr(app_module, "create_engine_from_settings", lambda current: object())
    monkeypatch.setattr(app_module, "verify_database_connection", lambda engine: None)
    monkeypatch.setattr(
        app_module,
        "ensure_database_schema",
        lambda engine, *, settings: SchemaState(
            current_revision="ebbb78f282b7",
            expected_revision="ebbb78f282b7",
            has_version_table=True,
            has_application_tables=True,
        ),
    )
    monkeypatch.setattr(app_module, "create_session_factory", lambda engine: lambda: None)

    with caplog.at_level(logging.INFO):
        app_module.create_app(settings)

    assert "Using postgres on host postgres database backend" in caplog.text
    assert "password" not in caplog.text


def test_upgrade_database_from_settings_creates_expected_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "migrated.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        auto_create_schema=False,
        _env_file=None,
    )
    engine = session_module.create_engine_from_settings(settings)

    session_module.upgrade_database_from_settings(settings)
    schema_state = get_schema_state(engine, settings.database_url)

    assert schema_state.is_at_head is True
    assert "custom_entities" in inspect(engine).get_table_names()
    assert "patterns" in inspect(engine).get_table_names()


def test_upgrade_database_from_settings_stamps_legacy_bootstrap_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        auto_create_schema=False,
        _env_file=None,
    )
    engine = session_module.create_engine_from_settings(settings)

    session_module.load_model_metadata()
    Base.metadata.create_all(bind=engine)
    assert get_schema_state(engine, settings.database_url).current_revision is None

    session_module.upgrade_database_from_settings(settings)
    schema_state = get_schema_state(engine, settings.database_url)

    assert schema_state.is_at_head is True
    assert schema_state.has_version_table is True


def test_ensure_database_schema_applies_migrations_when_enabled(tmp_path: Path) -> None:
    database_path = tmp_path / "auto-upgrade.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        auto_create_schema=True,
        _env_file=None,
    )
    engine = session_module.create_engine_from_settings(settings)

    schema_state = session_module.ensure_database_schema(engine, settings=settings)

    assert schema_state.is_at_head is True
    assert "patterns" in inspect(engine).get_table_names()


def test_ensure_database_schema_rejects_uninitialized_database_when_disabled(tmp_path: Path) -> None:
    database_path = tmp_path / "missing-schema.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        auto_create_schema=False,
        _env_file=None,
    )
    engine = session_module.create_engine_from_settings(settings)

    with pytest.raises(RuntimeError, match="Apply Alembic migrations"):
        session_module.ensure_database_schema(engine, settings=settings)


def test_app_startup_rejects_missing_schema_when_bootstrap_disabled(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'app-missing.db').as_posix()}",
        storage_root=tmp_path / "storage",
        auto_create_schema=False,
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="Apply Alembic migrations"):
        app_module.create_app(settings)
