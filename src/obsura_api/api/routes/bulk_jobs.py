"""Routes for persisted bulk text submissions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_container, get_db_session, get_pagination_params, get_settings
from obsura_api.api.responses import success_response
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings
from obsura_api.domain.bulk import (
    BulkJobRead,
    BulkJobReviewRequest,
    BulkJobSummaryRead,
    BulkReviewResponse,
    BulkTextAnalyzeRequest,
    BulkTextTransformRequest,
    BulkTextTransformResponse,
)
from obsura_api.domain.common import ApiResponse, PaginationParams
from obsura_api.services.bulk_jobs import BulkJobService

router = APIRouter(prefix="/bulk", tags=["bulk-jobs"])
SessionDep = Annotated[Session, Depends(get_db_session)]
PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]


@router.post(
    "/text/analyze",
    response_model=ApiResponse[BulkJobRead],
    status_code=status.HTTP_201_CREATED,
)
def analyze_bulk_text(
    payload: BulkTextAnalyzeRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[BulkJobRead]:
    """Analyze many text items, persist one bulk job, and create reviewable child jobs."""

    return success_response(
        BulkJobService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).analyze_text(payload),
    )


@router.get("/jobs", response_model=ApiResponse[list[BulkJobSummaryRead]])
def list_bulk_jobs(
    session: SessionDep,
    pagination: PaginationDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[list[BulkJobSummaryRead]]:
    """List persisted bulk text jobs with summary counts and status."""

    items, pagination_meta = BulkJobService(
        session,
        settings,
        pii_detector=container.pii_detector,
        text_anonymizer=container.text_anonymizer,
    ).list_bulk_jobs(pagination)
    return success_response(items, pagination=pagination_meta)


@router.get("/jobs/{bulk_id}", response_model=ApiResponse[BulkJobRead])
def get_bulk_job(
    bulk_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[BulkJobRead]:
    """Fetch one persisted bulk text job in detail, including per-item outcomes."""

    return success_response(
        BulkJobService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).get_bulk_job(str(bulk_id)),
    )


@router.post("/jobs/{bulk_id}/review", response_model=ApiResponse[BulkReviewResponse])
def review_bulk_job(
    bulk_id: UUID,
    payload: BulkJobReviewRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[BulkReviewResponse]:
    """Apply review decisions across child jobs that belong to one bulk run."""

    return success_response(
        BulkJobService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).review_bulk_job(str(bulk_id), payload),
    )


@router.post("/text/transform", response_model=ApiResponse[BulkTextTransformResponse])
def transform_bulk_text(
    payload: BulkTextTransformRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[BulkTextTransformResponse]:
    """Transform text outputs across one persisted bulk run while preserving per-item outcomes."""

    return success_response(
        BulkJobService(
            session,
            settings,
            pii_detector=container.pii_detector,
            text_anonymizer=container.text_anonymizer,
        ).transform_text(payload),
    )
