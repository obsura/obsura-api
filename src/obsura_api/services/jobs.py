"""Job history and review services."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from obsura_api.db.models import Job, JobFinding, JobOutput
from obsura_api.domain.common import BoundingBox
from obsura_api.domain.enums import JobStatus
from obsura_api.domain.jobs import JobOutputRecord, JobRead, JobReviewRequest
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord
from obsura_api.services.utils import summarize_findings


def finding_to_schema(finding: JobFinding) -> FindingRecord:
    """Convert a stored finding into an API model."""

    return FindingRecord(
        id=finding.id,
        job_id=finding.job_id,
        source=finding.source,
        kind=finding.kind,
        entity_type=finding.entity_type,
        entity_name=finding.entity_name,
        start_index=finding.start_index,
        end_index=finding.end_index,
        region=BoundingBox.model_validate(finding.region) if finding.region else None,
        matched_text_preview=finding.matched_text_preview,
        matched_text_hash=finding.matched_text_hash,
        confidence=finding.confidence,
        decision=finding.decision,
        transformation=(
            TransformationRule.model_validate(finding.transformation)
            if finding.transformation
            else None
        ),
        metadata=finding.extra_data,
    )


def output_to_schema(output: JobOutput) -> JobOutputRecord:
    """Convert a stored job output into an API model."""

    return JobOutputRecord(
        id=output.id,
        created_at=output.created_at,
        updated_at=output.updated_at,
        job_id=output.job_id,
        content_type=output.content_type,
        output_text=output.output_text,
        output_file_path=output.output_file_path,
        metadata=output.extra_data,
    )


def job_to_schema(job: Job) -> JobRead:
    """Convert a stored job and its relationships into an API model."""

    findings = [finding_to_schema(item) for item in job.findings]
    outputs = [output_to_schema(item) for item in job.outputs]
    return JobRead(
        id=job.id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        title=job.title,
        status=job.status,
        content_type=job.content_type,
        source_text=job.source_text,
        source_file_path=job.source_file_path,
        pattern_ids=job.pattern_ids,
        custom_entity_ids=job.custom_entity_ids,
        configuration_ids=job.configuration_ids,
        summary=job.summary or summarize_findings(findings),
        findings=findings,
        outputs=outputs,
    )


class JobService:
    """Inspect and update stored jobs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_jobs(self) -> list[JobRead]:
        jobs = self.session.scalars(
            select(Job)
            .options(selectinload(Job.findings), selectinload(Job.outputs))
            .order_by(Job.created_at.desc()),
        ).all()
        return [job_to_schema(job) for job in jobs]

    def get_job(self, job_id: str) -> JobRead:
        job = self.session.scalar(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.findings), selectinload(Job.outputs)),
        )
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job_to_schema(job)

    def review_job(self, job_id: str, payload: JobReviewRequest) -> JobRead:
        job = self.session.scalar(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.findings), selectinload(Job.outputs)),
        )
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")

        by_id = {finding.id: finding for finding in job.findings}
        for decision in payload.decisions:
            finding = by_id.get(decision.finding_id)
            if finding is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"Finding {decision.finding_id} not found",
                )
            finding.decision = decision.decision
            if decision.transformation is not None:
                finding.transformation = decision.transformation.model_dump()

        job.status = JobStatus.REVIEWED
        findings = [finding_to_schema(item) for item in job.findings]
        job.summary = summarize_findings(findings)
        self.session.commit()
        self.session.refresh(job)
        return self.get_job(job.id)

