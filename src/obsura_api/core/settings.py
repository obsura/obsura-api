"""Application settings and environment loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DEVELOPMENT_DATABASE_URL = "sqlite:///./data/obsura.db"


class Settings(BaseSettings):
    """Runtime settings for the Obsura API process."""

    model_config = SettingsConfigDict(
        env_prefix="OBSURA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Obsura API"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("OBSURA_ENV", "OBSURA_ENVIRONMENT"),
    )
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "OBSURA_DATABASE_URL"),
    )
    face_detector_backend: str = Field(
        default="noop",
        validation_alias=AliasChoices(
            "OBSURA_FACE_DETECTOR_BACKEND",
            "OBSURA_FACE_DETECTOR",
        ),
    )
    storage_root: Path = Field(default=Path("storage"))
    media_mount_path: str = "/media"
    auto_create_schema: bool = True
    retain_source_content_by_default: bool = False
    image_output_format: str = "PNG"

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        raw_database_url = self.database_url.strip()

        if not raw_database_url:
            if self.is_production:
                raise ValueError(
                    "Production environment requires DATABASE_URL or "
                    "OBSURA_DATABASE_URL with a PostgreSQL URL.",
                )
            raw_database_url = DEFAULT_DEVELOPMENT_DATABASE_URL

        try:
            parsed_url = make_url(raw_database_url)
        except ArgumentError as exc:
            raise ValueError(f"Invalid database URL: {exc}") from exc

        if self.is_production and not parsed_url.drivername.startswith("postgresql"):
            raise ValueError(
                "Production environment requires a PostgreSQL DATABASE_URL or "
                "OBSURA_DATABASE_URL.",
            )

        self.database_url = parsed_url.render_as_string(hide_password=False)
        return self

    @property
    def upload_root(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def output_root(self) -> Path:
        return self.storage_root / "outputs"

    @property
    def normalized_environment(self) -> str:
        return self.environment.strip().lower()

    @property
    def is_production(self) -> bool:
        return self.normalized_environment == "production"

    @property
    def database_backend_summary(self) -> str:
        parsed_url = make_url(self.database_url)
        if parsed_url.drivername.startswith("postgresql"):
            return f"postgres on host {parsed_url.host or 'unknown'}"
        if parsed_url.drivername.startswith("sqlite"):
            if parsed_url.database in {None, "", ":memory:"}:
                return "sqlite in-memory"
            return f"sqlite at {parsed_url.database}"
        backend_name = parsed_url.get_backend_name()
        if parsed_url.host:
            return f"{backend_name} on host {parsed_url.host}"
        return backend_name


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object for the current process."""

    return Settings()
