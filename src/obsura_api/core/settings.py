"""Application settings and environment loading."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DEVELOPMENT_DATABASE_URL = "sqlite:///./data/obsura.db"
POSTGRES_DRIVER_ALIASES = {
    "postgres": "postgresql+psycopg",
    "postgresql": "postgresql+psycopg",
    "postgresql+psycopg2": "postgresql+psycopg",
}


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
    ocr_backend: str = Field(
        default="noop",
        validation_alias=AliasChoices(
            "OBSURA_OCR_BACKEND",
            "OBSURA_OCR_PROVIDER",
        ),
    )
    ocr_language: str = Field(
        default="eng",
        validation_alias=AliasChoices(
            "OBSURA_OCR_LANGUAGE",
            "OBSURA_TESSERACT_LANG",
        ),
    )
    pii_backend: str = Field(
        default="noop",
        validation_alias=AliasChoices(
            "OBSURA_PII_BACKEND",
            "OBSURA_PII_PROVIDER",
            "OBSURA_NLP_BACKEND",
        ),
    )
    pii_language: str = Field(
        default="en",
        validation_alias=AliasChoices(
            "OBSURA_PII_LANGUAGE",
            "OBSURA_PRESIDIO_LANGUAGE",
        ),
    )
    presidio_model: str = Field(
        default="en_core_web_sm",
        validation_alias=AliasChoices(
            "OBSURA_PRESIDIO_MODEL",
            "OBSURA_PII_MODEL",
        ),
    )
    presidio_score_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "OBSURA_PRESIDIO_SCORE_THRESHOLD",
            "OBSURA_PII_SCORE_THRESHOLD",
        ),
    )
    presidio_supported_languages: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(),
        validation_alias=AliasChoices(
            "OBSURA_PRESIDIO_SUPPORTED_LANGUAGES",
            "OBSURA_PII_SUPPORTED_LANGUAGES",
        ),
    )
    presidio_model_map: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict,
        validation_alias=AliasChoices(
            "OBSURA_PRESIDIO_MODEL_MAP",
            "OBSURA_PII_MODEL_MAP",
        ),
    )
    presidio_recognizers_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OBSURA_PRESIDIO_RECOGNIZERS_PATH",
            "OBSURA_PII_RECOGNIZERS_PATH",
        ),
    )
    text_anonymizer_backend: str = Field(
        default="auto",
        validation_alias=AliasChoices(
            "OBSURA_TEXT_ANONYMIZER_BACKEND",
            "OBSURA_PRESIDIO_ANONYMIZER_BACKEND",
        ),
    )
    text_hash_salt: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OBSURA_TEXT_HASH_SALT",
            "OBSURA_PRESIDIO_HASH_SALT",
        ),
    )
    storage_root: Path = Field(default=Path("storage"))
    media_mount_path: str = "/media"
    auto_create_schema: bool = False
    retain_source_content_by_default: bool = False
    image_output_format: str = "PNG"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_image_pixels: int = Field(default=20_000_000, ge=1)
    max_ephemeral_artifacts: int = Field(
        default=256,
        ge=1,
        le=4096,
        validation_alias=AliasChoices(
            "OBSURA_MAX_EPHEMERAL_ARTIFACTS",
            "OBSURA_EPHEMERAL_MEDIA_MAX_ITEMS",
        ),
    )
    ephemeral_artifact_ttl_seconds: int = Field(
        default=900,
        ge=1,
        le=86_400,
        validation_alias=AliasChoices(
            "OBSURA_EPHEMERAL_ARTIFACT_TTL_SECONDS",
            "OBSURA_MEDIA_TTL_SECONDS",
        ),
    )
    max_bulk_text_items: int = Field(default=50, ge=1, le=500)
    max_bulk_text_item_characters: int = Field(default=100_000, ge=1)
    max_bulk_text_total_characters: int = Field(default=1_000_000, ge=1)
    max_structured_payload_nodes: int = Field(default=5_000, ge=1, le=100_000)
    max_structured_payload_depth: int = Field(default=16, ge=1, le=128)
    max_structured_payload_characters: int = Field(default=250_000, ge=1)
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("http://127.0.0.1:3000", "http://localhost:3000"),
        validation_alias=AliasChoices(
            "OBSURA_CORS_ALLOWED_ORIGINS",
            "CORS_ALLOWED_ORIGINS",
            "OBSURA_ALLOWED_HOSTS",
            "ALLOWED_HOSTS",
        ),
    )
    cors_allow_credentials: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "OBSURA_CORS_ALLOW_CREDENTIALS",
            "CORS_ALLOW_CREDENTIALS",
        ),
    )

    @staticmethod
    def _normalize_database_driver(raw_database_url: str) -> str:
        """Normalize supported database URL aliases to the installed driver."""

        parsed_url = make_url(raw_database_url)
        normalized_driver = POSTGRES_DRIVER_ALIASES.get(parsed_url.drivername)
        if normalized_driver:
            parsed_url = parsed_url.set(drivername=normalized_driver)
        return parsed_url.render_as_string(hide_password=False)

    @staticmethod
    def _normalize_cors_origin(origin: str) -> str:
        normalized_origin = origin.strip()
        if normalized_origin != "*":
            normalized_origin = normalized_origin.rstrip("/")
        return normalized_origin

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: Any) -> Any:
        if value is None:
            return value

        if isinstance(value, str):
            raw_value = value.strip()
            if not raw_value:
                return ()
            if raw_value.startswith("["):
                try:
                    value = json.loads(raw_value)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "CORS allowed origins must be a JSON array or a comma-separated string.",
                    ) from exc
            else:
                value = raw_value.split(",")

        if isinstance(value, (list, tuple, set)):
            normalized_origins: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("CORS allowed origins entries must be strings.")
                origin = cls._normalize_cors_origin(item)
                if not origin:
                    continue
                if origin != "*" and "://" not in origin:
                    raise ValueError(
                        "CORS allowed origins must include a scheme, for example http://127.0.0.1:3000.",
                    )
                if origin not in normalized_origins:
                    normalized_origins.append(origin)
            return tuple(normalized_origins)

        return value

    @field_validator("presidio_supported_languages", mode="before")
    @classmethod
    def parse_presidio_supported_languages(cls, value: Any) -> Any:
        if value is None:
            return ()

        if isinstance(value, str):
            raw_value = value.strip()
            if not raw_value:
                return ()
            if raw_value.startswith("["):
                try:
                    value = json.loads(raw_value)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "Presidio supported languages must be a JSON array or comma-separated string.",
                    ) from exc
            else:
                value = raw_value.split(",")

        if isinstance(value, (list, tuple, set)):
            normalized: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("Presidio supported languages entries must be strings.")
                language = item.strip().lower()
                if not language or language in normalized:
                    continue
                normalized.append(language)
            return tuple(normalized)

        return value

    @field_validator("presidio_model_map", mode="before")
    @classmethod
    def parse_presidio_model_map(cls, value: Any) -> Any:
        if value is None or value == "":
            return {}

        if isinstance(value, str):
            raw_value = value.strip()
            if not raw_value:
                return {}
            if raw_value.startswith("{"):
                try:
                    value = json.loads(raw_value)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "Presidio model map must be a JSON object or comma-separated lang=model pairs.",
                    ) from exc
            else:
                parsed: dict[str, str] = {}
                for item in raw_value.split(","):
                    if "=" not in item:
                        raise ValueError(
                            "Presidio model map entries must use the `lang=model_name` format.",
                        )
                    language, model_name = item.split("=", 1)
                    normalized_language = language.strip().lower()
                    normalized_model = model_name.strip()
                    if not normalized_language or not normalized_model:
                        raise ValueError("Presidio model map entries must include both language and model.")
                    parsed[normalized_language] = normalized_model
                return parsed

        if isinstance(value, dict):
            normalized: dict[str, str] = {}
            for language, model_name in value.items():
                if not isinstance(language, str) or not isinstance(model_name, str):
                    raise ValueError("Presidio model map keys and values must be strings.")
                normalized_language = language.strip().lower()
                normalized_model = model_name.strip()
                if not normalized_language or not normalized_model:
                    raise ValueError("Presidio model map entries must not be blank.")
                normalized[normalized_language] = normalized_model
            return normalized

        return value

    @field_validator("presidio_recognizers_path", mode="before")
    @classmethod
    def parse_presidio_recognizers_path(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            return Path(normalized)
        return value

    @field_validator("text_hash_salt", mode="before")
    @classmethod
    def parse_text_hash_salt(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

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
            normalized_database_url = self._normalize_database_driver(raw_database_url)
            parsed_url = make_url(normalized_database_url)
        except ArgumentError as exc:
            raise ValueError(f"Invalid database URL: {exc}") from exc

        if self.is_production and not parsed_url.drivername.startswith("postgresql"):
            raise ValueError(
                "Production environment requires a PostgreSQL DATABASE_URL or "
                "OBSURA_DATABASE_URL.",
            )
        if self.is_production and self.auto_create_schema:
            raise ValueError(
                "Production environment must not use OBSURA_AUTO_CREATE_SCHEMA=true. "
                "Apply Alembic migrations explicitly before starting the API.",
            )
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError(
                "OBSURA_CORS_ALLOWED_ORIGINS must not include '*' when "
                "OBSURA_CORS_ALLOW_CREDENTIALS=true.",
            )

        normalized_pii_language = self.pii_language.strip().lower()
        self.pii_language = normalized_pii_language
        if self.presidio_recognizers_path is not None:
            self.presidio_recognizers_path = self.presidio_recognizers_path.expanduser()

        normalized_languages = list(self.presidio_supported_languages)
        if normalized_pii_language and normalized_pii_language not in normalized_languages:
            normalized_languages.insert(0, normalized_pii_language)
        self.presidio_supported_languages = tuple(normalized_languages)

        normalized_model_map = dict(self.presidio_model_map)
        if normalized_pii_language and self.presidio_model and normalized_pii_language not in normalized_model_map:
            normalized_model_map[normalized_pii_language] = self.presidio_model.strip()
        self.presidio_model_map = normalized_model_map

        if self.pii_backend.strip().lower() in {"presidio", "presidio_analyzer"}:
            missing_languages = [
                language
                for language in self.presidio_supported_languages
                if language not in self.presidio_model_map
            ]
            if missing_languages:
                missing = ", ".join(missing_languages)
                raise ValueError(
                    "Presidio requires a spaCy model for each configured language. "
                    f"Missing model mapping for: {missing}",
                )

        self.text_anonymizer_backend = self.text_anonymizer_backend.strip().lower()
        if self.text_hash_salt is not None and len(self.text_hash_salt.encode("utf-8")) < 16:
            raise ValueError("OBSURA_TEXT_HASH_SALT must be at least 16 bytes long.")

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
