"""Health and metadata endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from obsura_api import __version__
from obsura_api.api.dependencies import get_container, get_settings
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings
from obsura_api.db.migrations import describe_schema_mismatch, get_schema_state
from obsura_api.db.session import verify_database_connection
from obsura_api.api.responses import success_response
from obsura_api.domain.common import ApiResponse
from obsura_api.domain.operational import ServiceVersionInfo

router = APIRouter(tags=["health"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def healthcheck() -> ApiResponse[dict[str, str]]:
    """Simple liveness response."""

    return success_response({"status": "ok"})


@router.get("/ready", response_model=ApiResponse[dict[str, str]])
def readiness(
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[dict[str, str]]:
    """Dependency-aware readiness response."""

    try:
        verify_database_connection(container.engine)
        schema_state = get_schema_state(container.engine, settings.database_url)
        if not schema_state.is_at_head:
            raise RuntimeError(describe_schema_mismatch(schema_state))
        container.storage.assert_ready()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return success_response(
        {
            "status": "ready",
            "environment": settings.normalized_environment,
        }
    )


@router.get("/version", response_model=ApiResponse[ServiceVersionInfo])
def version(settings: SettingsDep, container: ContainerDep) -> ApiResponse[ServiceVersionInfo]:
    """Return service version and runtime metadata."""

    schema_state = get_schema_state(container.engine, settings.database_url)
    return success_response(
        ServiceVersionInfo(
            name=settings.app_name,
            version=__version__,
            environment=settings.normalized_environment,
            database_backend=settings.database_backend_summary,
            schema_revision=schema_state.current_revision or "uninitialized",
            schema_head=schema_state.expected_revision,
            ocr_backend=container.ocr_provider.name,
            face_detector_backend=container.face_detector.name,
            pii_backend=container.pii_detector.name,
            text_anonymizer_backend=container.text_anonymizer.name,
            pii_languages=list(getattr(container.pii_detector, "supported_languages", ()) or ()),
            pii_custom_recognizers=bool(
                getattr(container.pii_detector, "custom_recognizers_configured", False),
            ),
            text_hash_supported=bool(getattr(container.text_anonymizer, "hash_supported", False)),
            ocr_available=container.ocr_provider.supported,
            face_detection_available=container.face_detector.supported,
            pii_available=container.pii_detector.supported,
        ),
    )
