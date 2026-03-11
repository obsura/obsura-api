"""Routes for text analysis and transformation workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_db_session, get_settings
from obsura_api.api.responses import success_response
from obsura_api.core.settings import Settings
from obsura_api.domain.common import ApiResponse
from obsura_api.domain.workflows import (
    TextAnalysisRequest,
    TextAnalysisResponse,
    TextTransformRequest,
    TextTransformResponse,
)
from obsura_api.services.detection import TextDetectionService
from obsura_api.services.text_transformations import TextTransformationService

router = APIRouter(prefix="/workflows/text", tags=["text-workflows"])
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/analyze", response_model=ApiResponse[TextAnalysisResponse])
def analyze_text(
    payload: TextAnalysisRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> ApiResponse[TextAnalysisResponse]:
    """Analyze text-like content into reviewable findings and optionally persist a job."""

    return success_response(TextDetectionService(session, settings).analyze(payload))


@router.post("/transform", response_model=ApiResponse[TextTransformResponse])
def transform_text(
    payload: TextTransformRequest,
    session: SessionDep,
) -> ApiResponse[TextTransformResponse]:
    """Transform a persisted text job after review decisions and overrides are applied."""

    return success_response(TextTransformationService(session).transform_job(payload))


@router.post("/analyze-transform", response_model=ApiResponse[TextTransformResponse])
def analyze_and_transform_text(
    payload: TextAnalysisRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> ApiResponse[TextTransformResponse]:
    """Run a one-shot analyze-plus-transform flow while still producing reviewable findings."""

    detector = TextDetectionService(session, settings)
    analysis = detector.analyze(payload)
    transformer = TextTransformationService(session)
    output_text, replacements = transformer.apply_findings(
        content=payload.content,
        findings=analysis.findings,
        include_pending=True,
        default_transformation=payload.default_transformation,
    )
    if analysis.job_id:
        transformer.persist_text_output(
            job_id=analysis.job_id,
            output_text=output_text,
            replacement_count=len(replacements),
        )
    return success_response(
        TextTransformResponse(
            job_id=analysis.job_id,
            output_text=output_text,
            replacements=replacements,
            summary={"replacement_count": len(replacements)},
        ),
    )
