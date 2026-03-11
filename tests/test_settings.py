from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from obsura_api import app as app_module
from obsura_api.core.settings import DEFAULT_DEVELOPMENT_DATABASE_URL, Settings, get_settings
from obsura_api.db import session as session_module


@pytest.fixture(autouse=True)
def clear_settings_env(monkeypatch) -> None:
    for key in (
        "DATABASE_URL",
        "OBSURA_DATABASE_URL",
        "OBSURA_ENV",
        "OBSURA_ENVIRONMENT",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def test_reads_database_url_from_canonical_env(monkeypatch) -> None:
    database_url = "postgresql+psycopg://obsura:password@postgres:5432/obsura"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == database_url


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


def test_development_allows_sqlite_fallback() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == DEFAULT_DEVELOPMENT_DATABASE_URL


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
    monkeypatch.setattr(app_module, "create_session_factory", lambda engine: lambda: None)

    with caplog.at_level(logging.INFO):
        app_module.create_app(settings)

    assert "Using postgres on host postgres database backend" in caplog.text
    assert "password" not in caplog.text
