"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image as PILImage
from starlette.exceptions import HTTPException as StarletteHTTPException

from obsura_api import __version__
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
from obsura_api.services.providers.pii import build_pii_detector
from obsura_api.services.providers.text_anonymizer import build_text_anonymizer
from obsura_api.services.privacy import scrub_persisted_sensitive_data
from obsura_api.services.storage import StorageService

logger = logging.getLogger(__name__)
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}

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
        "name": "structured-workflows",
        "description": "Review-first structured JSON workflows for nested payloads, records, and semi-structured application data.",
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
- structured JSON analyze/review/transform workflows
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
    scrubbed_disk_files = storage.purge_sensitive_storage()
    scrub_counts = {"jobs": 0, "outputs": 0, "findings": 0}
    session = session_factory()
    try:
        if session is not None:
            scrub_counts = scrub_persisted_sensitive_data(session)
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()
    ocr_provider = build_ocr_provider(settings)
    face_detector = build_face_detector(settings)
    pii_detector = build_pii_detector(settings)
    text_anonymizer = build_text_anonymizer(settings)
    PILImage.MAX_IMAGE_PIXELS = settings.max_image_pixels
    logger.info("Using `%s` OCR backend", ocr_provider.name)
    logger.info("Using `%s` face detector backend", face_detector.name)
    logger.info("Using `%s` PII detector backend", pii_detector.name)
    logger.info(
        "Using `%s` text anonymizer backend (hash supported: %s)",
        text_anonymizer.name,
        bool(getattr(text_anonymizer, "hash_supported", False)),
    )
    if getattr(pii_detector, "supported_languages", ()):
        logger.info(
            "PII detector languages: %s (custom recognizers: %s)",
            ", ".join(getattr(pii_detector, "supported_languages", ())),
            bool(getattr(pii_detector, "custom_recognizers_configured", False)),
        )
    logger.info(
        "Sensitive data scrub completed: %s jobs, %s outputs, %s findings, %s disk files",
        scrub_counts["jobs"],
        scrub_counts["outputs"],
        scrub_counts["findings"],
        scrubbed_disk_files,
    )

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

    @app.middleware("http")
    async def secure_response_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in NO_STORE_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

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
            pii_available=pii_detector.supported,
        )

    app.state.container = AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        storage=storage,
        ocr_provider=ocr_provider,
        face_detector=face_detector,
        pii_detector=pii_detector,
        text_anonymizer=text_anonymizer,
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get(f"{settings.media_mount_path}" + "/{artifact_path:path}", include_in_schema=False)
    def serve_media_artifact(artifact_path: str) -> Response:
        reference = artifact_path.lstrip("/")
        if not storage.is_public_reference(reference):
            raise HTTPException(status_code=404, detail="Media artifact not found")
        try:
            content = storage.read_stored_bytes(reference)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Media artifact not found") from exc
        return Response(
            content=content,
            media_type=storage.get_media_type(reference),
            headers=dict(NO_STORE_HEADERS),
        )

    return app
