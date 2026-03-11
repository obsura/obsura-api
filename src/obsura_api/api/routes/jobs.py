"""Routes for job history and review decisions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_db_session, get_pagination_params
from obsura_api.api.responses import success_response
from obsura_api.domain.common import ApiResponse, PaginationParams
from obsura_api.domain.jobs import JobRead, JobReviewRequest
from obsura_api.services.jobs import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])
SessionDep = Annotated[Session, Depends(get_db_session)]
PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]


@router.get("", response_model=ApiResponse[list[JobRead]])
def list_jobs(
    session: SessionDep,
    pagination: PaginationDep,
) -> ApiResponse[list[JobRead]]:
    """List persisted jobs with findings and generated outputs."""

    items, pagination_meta = JobService(session).list_jobs(pagination)
    return success_response(items, pagination=pagination_meta)


@router.get("/{job_id}", response_model=ApiResponse[JobRead])
def get_job(job_id: str, session: SessionDep) -> ApiResponse[JobRead]:
    """Fetch one persisted job by identifier."""

    return success_response(JobService(session).get_job(job_id))


@router.post("/{job_id}/review", response_model=ApiResponse[JobRead])
def review_job(
    job_id: str,
    payload: JobReviewRequest,
    session: SessionDep,
) -> ApiResponse[JobRead]:
    """Apply review decisions to findings within a persisted job."""

    return success_response(JobService(session).review_job(job_id, payload))
