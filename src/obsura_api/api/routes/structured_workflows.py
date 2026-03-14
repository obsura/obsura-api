"""Routes for structured JSON analysis and transformation workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_container, get_db_session, get_settings
from obsura_api.api.responses import success_response
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings
from obsura_api.domain.common import ApiResponse
from obsura_api.domain.structured import (
    StructuredAnalysisRequest,
    StructuredJobTransformRequest,
    StructuredTransformRequest,
    StructuredWorkflowResponse,
)
from obsura_api.services.structured_workflows import StructuredWorkflowService

router = APIRouter(prefix="/workflows/structured", tags=["structured-workflows"])
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]


@router.post("/analyze", response_model=ApiResponse[StructuredWorkflowResponse])
def analyze_structured(
    payload: StructuredAnalysisRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[StructuredWorkflowResponse]:
    """Analyze structured JSON content into reviewable field findings."""

    return success_response(
        StructuredWorkflowService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).analyze(payload),
    )


@router.post("/transform", response_model=ApiResponse[StructuredWorkflowResponse])
def transform_structured(
    payload: StructuredTransformRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[StructuredWorkflowResponse]:
    """Analyze and transform structured JSON content in one request."""

    return success_response(
        StructuredWorkflowService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).transform(payload),
    )


@router.post("/transform-job", response_model=ApiResponse[StructuredWorkflowResponse])
def transform_structured_job(
    payload: StructuredJobTransformRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[StructuredWorkflowResponse]:
    """Transform a persisted structured job after review and overrides."""

    return success_response(
        StructuredWorkflowService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).transform_job(payload),
    )
