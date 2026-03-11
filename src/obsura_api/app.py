"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from obsura_api import __version__
from obsura_api.api.router import api_router
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings, get_settings
from obsura_api.db import models as _models  # noqa: F401
from obsura_api.db.session import create_engine_from_settings, create_session_factory, initialize_database
from obsura_api.services.providers.faces import NoOpFaceDetector
from obsura_api.services.providers.ocr import NoOpOCRProvider
from obsura_api.services.storage import StorageService

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Service health and platform metadata endpoints.",
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
- reviewable jobs and run history
- text-first and screenshot-first sanitization workflows
- transformation behavior beyond plain placeholder replacement
- image-region protection flows for blur, pixelation, masks, and overlays

This OpenAPI document is intended for direct import into API clients such as Postman.
""".strip()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application and shared runtime container."""

    settings = settings or get_settings()
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    storage = StorageService(settings)
    if settings.auto_create_schema:
        initialize_database(engine)

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

    app.state.container = AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        storage=storage,
        ocr_provider=NoOpOCRProvider(),
        face_detector=NoOpFaceDetector(),
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.mount(
        settings.media_mount_path,
        StaticFiles(directory=settings.storage_root),
        name="media",
    )
    return app
