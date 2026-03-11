"""Routes for job history and review decisions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_db_session
from obsura_api.domain.jobs import JobRead, JobReviewRequest
from obsura_api.services.jobs import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[JobRead])
def list_jobs(session: SessionDep) -> list[JobRead]:
    """List persisted jobs with findings and generated outputs."""

    return JobService(session).list_jobs()


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: SessionDep) -> JobRead:
    """Fetch one persisted job by identifier."""

    return JobService(session).get_job(job_id)


@router.post("/{job_id}/review", response_model=JobRead)
def review_job(
    job_id: str,
    payload: JobReviewRequest,
    session: SessionDep,
) -> JobRead:
    """Apply review decisions to findings within a persisted job."""

    return JobService(session).review_job(job_id, payload)
