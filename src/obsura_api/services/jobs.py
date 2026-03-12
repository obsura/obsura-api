"""Job history and review services."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from obsura_api.db.models import Job, JobFinding, JobOutput
from obsura_api.domain.common import BoundingBox, PaginationMeta, PaginationParams, build_pagination_meta
from obsura_api.domain.enums import JobStatus
from obsura_api.domain.jobs import JobOutputRecord, JobRead, JobReviewRequest
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord
from obsura_api.services.storage import StorageService
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


def output_to_schema(
    output: JobOutput,
    *,
    storage: StorageService | None = None,
) -> JobOutputRecord:
    """Convert a stored job output into an API model."""

    output_file_path = _storage_reference(storage, output.output_file_path)
    media_url = None
    if storage is not None and output.output_file_path:
        media_url = storage.media_url_for(output.output_file_path)
    return JobOutputRecord(
        id=output.id,
        created_at=output.created_at,
        updated_at=output.updated_at,
        job_id=output.job_id,
        content_type=output.content_type,
        output_text=output.output_text,
        output_file_path=output_file_path,
        media_url=media_url,
        metadata=output.extra_data,
    )


def job_to_schema(job: Job, *, storage: StorageService | None = None) -> JobRead:
    """Convert a stored job and its relationships into an API model."""

    findings = [finding_to_schema(item) for item in job.findings]
    outputs = [output_to_schema(item, storage=storage) for item in job.outputs]
    return JobRead(
        id=job.id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        title=job.title,
        status=job.status,
        content_type=job.content_type,
        source_text=job.source_text,
        source_file_path=_storage_reference(storage, job.source_file_path),
        pattern_ids=job.pattern_ids,
        custom_entity_ids=job.custom_entity_ids,
        configuration_ids=job.configuration_ids,
        summary=job.summary or summarize_findings(findings),
        findings=findings,
        outputs=outputs,
    )


def _storage_reference(storage: StorageService | None, raw_path: str | None) -> str | None:
    if raw_path is None:
        return None
    if storage is None:
        return raw_path
    return storage.storage_reference_for(raw_path)


class JobService:
    """Inspect and update stored jobs."""

    def __init__(self, session: Session, storage: StorageService | None = None) -> None:
        self.session = session
        self.storage = storage

    def list_jobs(self, pagination: PaginationParams) -> tuple[list[JobRead], PaginationMeta]:
        total_items = self.session.scalar(select(func.count()).select_from(Job)) or 0
        jobs = self.session.scalars(
            select(Job)
            .options(selectinload(Job.findings), selectinload(Job.outputs))
            .order_by(Job.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size),
        ).all()
        return (
            [job_to_schema(job, storage=self.storage) for job in jobs],
            build_pagination_meta(params=pagination, total_items=total_items),
        )

    def get_job(self, job_id: str) -> JobRead:
        job = self._load_job_with_relations(job_id)
        return job_to_schema(job, storage=self.storage)

    def review_job(self, job_id: str, payload: JobReviewRequest) -> JobRead:
        job = self._load_job_with_relations(job_id)
        return self.apply_review_to_job(job, payload)

    def apply_review_to_job(
        self,
        job: Job,
        payload: JobReviewRequest,
        *,
        commit: bool = True,
    ) -> JobRead:
        """Apply review decisions to a loaded job."""

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
        if commit:
            self.session.commit()
            self.session.refresh(job)
        return job_to_schema(job, storage=self.storage)

    def _load_job_with_relations(self, job_id: str) -> Job:
        job = self.session.scalar(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.findings), selectinload(Job.outputs)),
        )
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job
