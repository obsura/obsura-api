"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from obsura_api import __version__
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from obsura_api.api.router import api_router
from obsura_api.api.responses import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings, get_settings
from obsura_api.db import models as _models  # noqa: F401
from obsura_api.db.session import (
    create_engine_from_settings,
    create_session_factory,
    ensure_database_schema,
    verify_database_connection,
)
from obsura_api.domain.operational import ServiceRootInfo
from obsura_api.services.providers.faces import build_face_detector
from obsura_api.services.providers.ocr import build_ocr_provider
from obsura_api.services.storage import StorageService

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Service health and platform metadata endpoints.",
    },
    {
        "name": "bulk-jobs",
        "description": "Review-first bulk text submissions that group multiple persisted child jobs under one parent run.",
    },
    {
        "name": "studio",
        "description": "Persistent studio assets such as patterns, custom entities, reusable packs, profiles, and presets.",
    },
    {
        "name": "jobs",
        "description": "Review history, job inspection, and review-decision updates.",
    },
    {
        "name": "text-workflows",
        "description": "Review-first text detection and transformation workflows for pasted text, logs, and structured technical content.",
    },
    {
        "name": "image-workflows",
        "description": "Screenshot and image-region workflows for manual regions, face-protection flows, and generated outputs.",
    },
]

OPENAPI_DESCRIPTION = """
Obsura API is the review-first workflow and orchestration layer for Obsura.

The API supports:
- persistent studio assets for custom detection and reusable configurations
- persisted bulk text submissions that group many reviewable child jobs
- reviewable jobs and run history
- text-first and screenshot-first sanitization workflows
- transformation behavior beyond plain placeholder replacement
- image-region protection flows for blur, pixelation, masks, and overlays

This OpenAPI document is intended for direct import into API clients such as Postman.
""".strip()


def _first_forwarded_value(value: str | None) -> str | None:
    if value is None:
        return None
    item = value.split(",", 1)[0].strip()
    return item or None


def _public_base_url(request: Request) -> str:
    scheme = _first_forwarded_value(request.headers.get("x-forwarded-proto")) or request.url.scheme
    host = _first_forwarded_value(request.headers.get("x-forwarded-host")) or request.headers.get(
        "host",
    )
    if not host:
        host = request.url.netloc
    return f"{scheme}://{host}"


def _public_url(base_url: str, path: str | None) -> str | None:
    if not path:
        return None
    return f"{base_url}{path}"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application and shared runtime container."""

    settings = settings or get_settings()
    logger.info(
        "Starting %s v%s in %s mode",
        settings.app_name,
        __version__,
        settings.normalized_environment,
    )
    logger.info("Using %s database backend", settings.database_backend_summary)
    if settings.auto_create_schema:
        logger.info("Automatic Alembic upgrade-on-startup is enabled for this environment")
    engine = create_engine_from_settings(settings)
    verify_database_connection(engine)
    schema_state = ensure_database_schema(engine, settings=settings)
    logger.info(
        "Database schema revision ready at %s",
        schema_state.current_revision,
    )
    session_factory = create_session_factory(engine)
    storage = StorageService(settings)
    storage.assert_ready()
    ocr_provider = build_ocr_provider(settings)
    face_detector = build_face_detector(settings)
    logger.info("Using `%s` OCR backend", ocr_provider.name)
    logger.info("Using `%s` face detector backend", face_detector.name)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Review-first sanitization workflows, studio assets, and job orchestration for Obsura.",
        description=OPENAPI_DESCRIPTION,
        contact={
            "name": "Obsura",
            "url": "https://github.com/obsura",
        },
        license_info={
            "name": "AGPL-3.0-or-later",
        },
        openapi_tags=OPENAPI_TAGS,
        servers=[
            {
                "url": "http://localhost:8000",
                "description": "Local development server",
            }
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/", include_in_schema=False, response_model=ServiceRootInfo)
    @app.get("/api", include_in_schema=False, response_model=ServiceRootInfo)
    def api_root(request: Request) -> ServiceRootInfo:
        public_base_url = _public_base_url(request)
        return ServiceRootInfo(
            name=settings.app_name,
            status="ok",
            docs_url=_public_url(public_base_url, app.docs_url),
            openapi_url=_public_url(public_base_url, app.openapi_url),
            version=f"v{__version__}",
            ocr_available=ocr_provider.supported,
            face_detection_available=face_detector.supported,
        )

    app.state.container = AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        storage=storage,
        ocr_provider=ocr_provider,
        face_detector=face_detector,
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.mount(
        settings.media_mount_path,
        StaticFiles(directory=settings.storage_root),
        name="media",
    )
    return app
