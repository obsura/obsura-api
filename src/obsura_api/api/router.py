"""Top-level API router assembly."""

from __future__ import annotations

from fastapi import APIRouter

from obsura_api.api.routes import (
    bulk_jobs,
    csv_workflows,
    document_workflows,
    health,
    image_workflows,
    jobs,
    structured_workflows,
    studio,
    text_workflows,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(bulk_jobs.router)
api_router.include_router(studio.router)
api_router.include_router(jobs.router)
api_router.include_router(csv_workflows.router)
api_router.include_router(document_workflows.router)
api_router.include_router(text_workflows.router)
api_router.include_router(structured_workflows.router)
api_router.include_router(image_workflows.router)
