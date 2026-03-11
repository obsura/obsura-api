"""Application settings and environment loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Obsura API process."""

    model_config = SettingsConfigDict(
        env_prefix="OBSURA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Obsura API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/obsura.db"
    storage_root: Path = Field(default=Path("storage"))
    media_mount_path: str = "/media"
    auto_create_schema: bool = True
    retain_source_content_by_default: bool = False
    image_output_format: str = "PNG"

    @property
    def upload_root(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def output_root(self) -> Path:
        return self.storage_root / "outputs"


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object for the current process."""

    return Settings()

