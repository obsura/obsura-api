"""Bulk text job services."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from obsura_api.core.settings import Settings
from obsura_api.db.models import BulkJob, BulkJobItem, Job, JobOutput
from obsura_api.domain.bulk import (
    BulkJobItemRead,
    BulkJobRead,
    BulkJobReviewRequest,
    BulkJobSummaryRead,
    BulkReviewItemResult,
    BulkReviewResponse,
    BulkTextAnalyzeRequest,
    BulkTextTransformItemResult,
    BulkTextTransformRequest,
    BulkTextTransformResponse,
)
from obsura_api.domain.common import PaginationMeta, PaginationParams, build_pagination_meta
from obsura_api.domain.enums import (
    BulkJobItemStatus,
    BulkJobStatus,
    BulkOperationItemStatus,
    BulkOperationKind,
    JobStatus,
)
from obsura_api.domain.jobs import JobReviewRequest
from obsura_api.domain.workflows import TextTransformRequest
from obsura_api.services.detection import TextDetectionService
from obsura_api.services.jobs import JobService
from obsura_api.services.providers.pii import NoOpPIIDetector, PIIDetector
from obsura_api.services.providers.text_anonymizer import NativeTextAnonymizer, TextAnonymizer
from obsura_api.services.text_transformations import TextTransformationService
from obsura_api.services.utils import summarize_findings


@dataclass(frozen=True, slots=True)
class BulkItemSnapshot:
    """Immutable identifier snapshot used across commit/rollback boundaries."""

    item_id: str
    item_index: int
    client_item_id: str | None
    title: str | None
    job_id: str | None


def empty_item_summary() -> dict[str, int]:
    """Return a consistent summary shape for failed or untouched bulk items."""

    return {
        "total": 0,
        "pending": 0,
        "approved": 0,
        "rejected": 0,
    }


def derive_bulk_item_status(item: BulkJobItem) -> BulkJobItemStatus:
    """Resolve the current lifecycle status for one bulk item."""

    if item.job is None:
        return BulkJobItemStatus.FAILED
    if item.job.status is JobStatus.TRANSFORMED or item.job.outputs:
        return BulkJobItemStatus.TRANSFORMED
    if item.job.status is JobStatus.REVIEWED:
        return BulkJobItemStatus.REVIEWED
    if item.status is BulkJobItemStatus.FAILED:
        return BulkJobItemStatus.FAILED
    return BulkJobItemStatus.SUCCEEDED


def summarize_bulk_progress(items: list[BulkJobItem]) -> tuple[int, int, int]:
    """Compute review/transform progress and stored output counts."""

    reviewed_item_count = 0
    transformed_item_count = 0
    output_count = 0

    for item in items:
        derived_status = derive_bulk_item_status(item)
        if derived_status in {BulkJobItemStatus.REVIEWED, BulkJobItemStatus.TRANSFORMED}:
            reviewed_item_count += 1
        if derived_status is BulkJobItemStatus.TRANSFORMED:
            transformed_item_count += 1
        if item.job is not None:
            output_count += len(item.job.outputs)

    return reviewed_item_count, transformed_item_count, output_count


def resolve_parent_status_from_items(items: list[BulkJobItem]) -> BulkJobStatus:
    """Resolve the bulk job lifecycle status from current item states."""

    total_items = len(items)
    failed_count = sum(
        1 for item in items if derive_bulk_item_status(item) is BulkJobItemStatus.FAILED
    )
    reviewed_item_count, transformed_item_count, _ = summarize_bulk_progress(items)
    successful_count = total_items - failed_count

    if total_items and transformed_item_count == total_items:
        return BulkJobStatus.TRANSFORMED
    if transformed_item_count > 0:
        return BulkJobStatus.PARTIALLY_TRANSFORMED
    if total_items and reviewed_item_count == total_items:
        return BulkJobStatus.REVIEWED
    if reviewed_item_count > 0:
        return BulkJobStatus.PARTIALLY_REVIEWED
    if successful_count > 0 and failed_count > 0:
        return BulkJobStatus.PARTIAL_FAILURE
    if successful_count > 0:
        return BulkJobStatus.COMPLETED
    return BulkJobStatus.FAILED


def item_summary(item: BulkJobItem) -> dict[str, int]:
    """Return the best available summary for one bulk item."""

    if item.job is not None and item.job.summary:
        return {
            **item.summary,
            **item.job.summary,
        }
    return item.summary or empty_item_summary()


def latest_output(item: BulkJobItem) -> JobOutput | None:
    """Return the most recent stored text output for one bulk item."""

    if item.job is None or not item.job.outputs:
        return None
    return max(item.job.outputs, key=lambda output: output.created_at)


def bulk_job_item_to_schema(item: BulkJobItem) -> BulkJobItemRead:
    """Convert one stored bulk item result into an API schema."""

    output = latest_output(item)
    return BulkJobItemRead(
        id=item.id,
        item_index=item.item_index,
        client_item_id=item.client_item_id,
        title=item.title,
        status=derive_bulk_item_status(item),
        job_id=item.job_id,
        job_status=item.job.status if item.job is not None else None,
        error=item.error_message,
        summary=item_summary(item),
        output_count=len(item.job.outputs) if item.job is not None else 0,
        output_available=output is not None,
    )


def bulk_job_to_summary_schema(item: BulkJob) -> BulkJobSummaryRead:
    """Convert a stored bulk job into the list summary schema."""

    return BulkJobSummaryRead.model_validate(item, from_attributes=True)


def bulk_job_to_schema(item: BulkJob) -> BulkJobRead:
    """Convert a stored bulk job into the detailed schema."""

    reviewed_item_count, transformed_item_count, output_count = summarize_bulk_progress(item.items)
    return BulkJobRead(
        id=item.id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        title=item.title,
        content_type=item.content_type,
        status=resolve_parent_status_from_items(item.items),
        item_count=item.item_count,
        success_count=item.success_count,
        failure_count=item.failure_count,
        reviewed_item_count=reviewed_item_count,
        transformed_item_count=transformed_item_count,
        output_count=output_count,
        items=[bulk_job_item_to_schema(child) for child in item.items],
    )


class BulkJobService:
    """Create, inspect, review, and transform persisted bulk text submissions."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        pii_detector: PIIDetector | None = None,
        *,
        text_anonymizer: TextAnonymizer | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.text_detection = TextDetectionService(
            session,
            settings,
            pii_detector=pii_detector or NoOpPIIDetector(),
        )
        self.job_service = JobService(session)
        self.text_transformations = TextTransformationService(
            session,
            settings,
            text_anonymizer=text_anonymizer
            or NativeTextAnonymizer(hash_salt=settings.text_hash_salt),
        )

    def analyze_text(self, payload: BulkTextAnalyzeRequest) -> BulkJobRead:
        self._validate_bulk_request(payload)
        (
            patterns,
            entities,
            resolved_pattern_ids,
            resolved_custom_entity_ids,
            resolved_configuration_ids,
            resolved_default_transformation,
            resolved_pii_detection,
        ) = self.text_detection.resolve_detection_context(
            content_type=payload.content_type,
            pattern_ids=payload.pattern_ids,
            custom_entity_ids=payload.custom_entity_ids,
            configuration_ids=payload.configuration_ids,
            default_transformation=payload.default_transformation,
            pii_detection=payload.pii_detection,
        )

        bulk_job = BulkJob(
            title=payload.title,
            content_type=payload.content_type,
            status=BulkJobStatus.FAILED,
            item_count=len(payload.items),
            success_count=0,
            failure_count=0,
        )
        self.session.add(bulk_job)
        self.session.flush()

        for item_index, item in enumerate(payload.items):
            normalized_title = item.title.strip() if item.title else None
            content = item.content or ""
            normalized_content = content.strip()
            error_message: str | None = None
            job_id: str | None = None
            summary: dict[str, int] = empty_item_summary()

            if not normalized_content:
                error_message = "Item content must not be blank"
            elif len(content) > self.settings.max_bulk_text_item_characters:
                error_message = (
                    "Item content exceeds the configured maximum of "
                    f"{self.settings.max_bulk_text_item_characters} characters"
                )
            else:
                findings = self.text_detection.build_findings(
                    content=content,
                    content_type=payload.content_type,
                    apply_builtins=payload.apply_builtins,
                    exact_values=payload.exact_values,
                    manual_spans=[],
                    patterns=patterns,
                    entities=entities,
                    default_transformation=resolved_default_transformation,
                    pii_detection=resolved_pii_detection,
                )
                summary = {
                    **empty_item_summary(),
                    **summarize_findings(findings),
                }
                job_id = self.text_detection.persist_analyzed_job(
                    title=normalized_title,
                    content_type=payload.content_type,
                    content=None,
                    pattern_ids=resolved_pattern_ids,
                    custom_entity_ids=resolved_custom_entity_ids,
                    configuration_ids=resolved_configuration_ids,
                    findings=findings,
                    commit=False,
                )

            item_status = (
                BulkJobItemStatus.FAILED
                if error_message is not None
                else BulkJobItemStatus.SUCCEEDED
            )
            bulk_item = BulkJobItem(
                bulk_job=bulk_job,
                item_index=item_index,
                client_item_id=item.client_item_id,
                title=normalized_title,
                status=item_status,
                job_id=job_id,
                error_message=error_message,
                summary=summary,
            )
            self.session.add(bulk_item)
            self.session.flush()

            if item_status is BulkJobItemStatus.SUCCEEDED:
                bulk_job.success_count += 1
            else:
                bulk_job.failure_count += 1

        bulk_job.status = resolve_parent_status_from_items(list(bulk_job.items))
        self.session.commit()
        return self.get_bulk_job(bulk_job.id)

    def list_bulk_jobs(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[BulkJobSummaryRead], PaginationMeta]:
        total_items = self.session.scalar(select(func.count()).select_from(BulkJob)) or 0
        items = self.session.scalars(
            select(BulkJob)
            .order_by(BulkJob.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size),
        ).all()
        return (
            [bulk_job_to_summary_schema(item) for item in items],
            build_pagination_meta(params=pagination, total_items=total_items),
        )

    def get_bulk_job(self, bulk_job_id: str) -> BulkJobRead:
        bulk_job = self._load_bulk_job_with_relations(bulk_job_id)
        return bulk_job_to_schema(bulk_job)

    def review_bulk_job(
        self, bulk_job_id: str, payload: BulkJobReviewRequest
    ) -> BulkReviewResponse:
        bulk_job = self._load_bulk_job_with_relations(bulk_job_id)
        snapshots = self._snapshot_items(bulk_job)
        entries_by_job_id = {entry.job_id: entry for entry in payload.jobs}
        self._validate_bulk_review_targets(snapshots, entries_by_job_id)

        items: list[BulkReviewItemResult] = []
        success_count = 0
        failure_count = 0
        skipped_count = 0

        for snapshot in snapshots:
            if snapshot.job_id is None:
                items.append(
                    self._build_review_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.FAILED,
                        error="No child job exists for this bulk item",
                        decision_count=0,
                    ),
                )
                failure_count += 1
                continue

            entry = entries_by_job_id.get(snapshot.job_id)
            if entry is None:
                items.append(
                    self._build_review_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.SKIPPED,
                        decision_count=0,
                    ),
                )
                skipped_count += 1
                continue

            try:
                job = self.job_service._load_job_with_relations(snapshot.job_id)
                self.job_service.apply_review_to_job(
                    job,
                    JobReviewRequest(decisions=entry.decisions),
                    commit=False,
                )
                item = self.session.get(BulkJobItem, snapshot.item_id)
                if item is not None:
                    item.status = BulkJobItemStatus.REVIEWED
                self.session.commit()
                items.append(
                    self._build_review_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.SUCCEEDED,
                        decision_count=len(entry.decisions),
                    ),
                )
                success_count += 1
            except HTTPException as exc:
                self.session.rollback()
                items.append(
                    self._build_review_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.FAILED,
                        error=self._error_message(exc),
                        decision_count=len(entry.decisions),
                    ),
                )
                failure_count += 1

        refreshed_bulk_job = self._load_bulk_job_with_relations(bulk_job_id)
        refreshed_bulk_job.status = resolve_parent_status_from_items(refreshed_bulk_job.items)
        self.session.commit()
        return self._build_review_response(
            refreshed_bulk_job,
            items=items,
            success_count=success_count,
            failure_count=failure_count,
            skipped_count=skipped_count,
        )

    def transform_text(self, payload: BulkTextTransformRequest) -> BulkTextTransformResponse:
        bulk_job = self._load_bulk_job_with_relations(payload.bulk_id)
        snapshots = self._snapshot_items(bulk_job)
        overrides_by_job_id = {item.job_id: item for item in payload.job_overrides}
        self._validate_bulk_transform_targets(snapshots, overrides_by_job_id)

        items: list[BulkTextTransformItemResult] = []
        success_count = 0
        failure_count = 0

        for snapshot in snapshots:
            if snapshot.job_id is None:
                items.append(
                    self._build_transform_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.FAILED,
                        error="No child job exists for this bulk item",
                    ),
                )
                failure_count += 1
                continue

            override = overrides_by_job_id.get(snapshot.job_id)
            transform_request = TextTransformRequest(
                job_id=snapshot.job_id,
                content=override.content if override is not None else None,
                finding_overrides=override.finding_overrides if override is not None else [],
                include_pending=payload.include_pending,
                default_transformation=payload.default_transformation,
                persist_output=payload.persist_output,
            )

            try:
                job = self.text_transformations._load_text_job(snapshot.job_id)
                transform_response = self.text_transformations.transform_loaded_job(
                    job,
                    transform_request,
                    commit=False,
                )
                if payload.persist_output:
                    item = self.session.get(BulkJobItem, snapshot.item_id)
                    if item is not None:
                        item.status = BulkJobItemStatus.TRANSFORMED
                self.session.commit()
                items.append(
                    self._build_transform_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.SUCCEEDED,
                        replacement_count=transform_response.summary.get("replacement_count", 0),
                        output_text=transform_response.output_text,
                    ),
                )
                success_count += 1
            except HTTPException as exc:
                self.session.rollback()
                items.append(
                    self._build_transform_result(
                        snapshot,
                        operation_status=BulkOperationItemStatus.FAILED,
                        error=self._error_message(exc),
                    ),
                )
                failure_count += 1

        refreshed_bulk_job = self._load_bulk_job_with_relations(payload.bulk_id)
        refreshed_bulk_job.status = resolve_parent_status_from_items(refreshed_bulk_job.items)
        self.session.commit()
        return self._build_transform_response(
            refreshed_bulk_job,
            items=items,
            success_count=success_count,
            failure_count=failure_count,
        )

    def _build_review_response(
        self,
        bulk_job: BulkJob,
        *,
        items: list[BulkReviewItemResult],
        success_count: int,
        failure_count: int,
        skipped_count: int,
    ) -> BulkReviewResponse:
        reviewed_item_count, transformed_item_count, output_count = summarize_bulk_progress(
            bulk_job.items
        )
        return BulkReviewResponse(
            bulk_id=bulk_job.id,
            action=BulkOperationKind.REVIEW,
            status=resolve_parent_status_from_items(bulk_job.items),
            item_count=len(bulk_job.items),
            success_count=success_count,
            failure_count=failure_count,
            skipped_count=skipped_count,
            reviewed_item_count=reviewed_item_count,
            transformed_item_count=transformed_item_count,
            output_count=output_count,
            items=items,
        )

    def _build_transform_response(
        self,
        bulk_job: BulkJob,
        *,
        items: list[BulkTextTransformItemResult],
        success_count: int,
        failure_count: int,
    ) -> BulkTextTransformResponse:
        reviewed_item_count, transformed_item_count, output_count = summarize_bulk_progress(
            bulk_job.items
        )
        return BulkTextTransformResponse(
            bulk_id=bulk_job.id,
            action=BulkOperationKind.TRANSFORM,
            status=resolve_parent_status_from_items(bulk_job.items),
            item_count=len(bulk_job.items),
            success_count=success_count,
            failure_count=failure_count,
            skipped_count=0,
            reviewed_item_count=reviewed_item_count,
            transformed_item_count=transformed_item_count,
            output_count=output_count,
            items=items,
        )

    def _build_review_result(
        self,
        snapshot: BulkItemSnapshot,
        *,
        operation_status: BulkOperationItemStatus,
        decision_count: int,
        error: str | None = None,
    ) -> BulkReviewItemResult:
        item = self._load_bulk_item(snapshot.item_id)
        payload = self._common_item_result_payload(
            item,
            operation_status=operation_status,
            error=error,
        )
        return BulkReviewItemResult(**payload, decision_count=decision_count)

    def _build_transform_result(
        self,
        snapshot: BulkItemSnapshot,
        *,
        operation_status: BulkOperationItemStatus,
        replacement_count: int = 0,
        output_text: str | None = None,
        error: str | None = None,
    ) -> BulkTextTransformItemResult:
        item = self._load_bulk_item(snapshot.item_id)
        payload = self._common_item_result_payload(
            item,
            operation_status=operation_status,
            error=error,
        )
        return BulkTextTransformItemResult(
            **payload,
            replacement_count=replacement_count,
            output_text=output_text,
        )

    def _common_item_result_payload(
        self,
        item: BulkJobItem,
        *,
        operation_status: BulkOperationItemStatus,
        error: str | None,
    ) -> dict[str, object]:
        output = latest_output(item)
        return {
            "id": item.id,
            "item_index": item.item_index,
            "client_item_id": item.client_item_id,
            "title": item.title,
            "job_id": item.job_id,
            "operation_status": operation_status,
            "bulk_item_status": derive_bulk_item_status(item),
            "job_status": item.job.status if item.job is not None else None,
            "error": error,
            "summary": item_summary(item),
            "output_count": len(item.job.outputs) if item.job is not None else 0,
            "output_available": output is not None,
        }

    def _load_bulk_job_with_relations(self, bulk_job_id: str) -> BulkJob:
        item_job_loader = selectinload(BulkJob.items).selectinload(BulkJobItem.job)
        bulk_job = self.session.scalar(
            select(BulkJob)
            .where(BulkJob.id == bulk_job_id)
            .execution_options(populate_existing=True)
            .options(
                item_job_loader.selectinload(Job.findings),
                item_job_loader.selectinload(Job.outputs),
            ),
        )
        if bulk_job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bulk job not found")
        return bulk_job

    def _load_bulk_item(self, item_id: str) -> BulkJobItem:
        item = self.session.scalar(
            select(BulkJobItem)
            .where(BulkJobItem.id == item_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(BulkJobItem.job).selectinload(Job.findings),
                selectinload(BulkJobItem.job).selectinload(Job.outputs),
            ),
        )
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bulk job item not found")
        return item

    def _snapshot_items(self, bulk_job: BulkJob) -> list[BulkItemSnapshot]:
        return [
            BulkItemSnapshot(
                item_id=item.id,
                item_index=item.item_index,
                client_item_id=item.client_item_id,
                title=item.title,
                job_id=item.job_id,
            )
            for item in sorted(bulk_job.items, key=lambda child: child.item_index)
        ]

    def _validate_bulk_request(self, payload: BulkTextAnalyzeRequest) -> None:
        if len(payload.items) > self.settings.max_bulk_text_items:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Bulk request exceeds the configured maximum of "
                    f"{self.settings.max_bulk_text_items} items"
                ),
            )
        total_characters = sum(len(item.content or "") for item in payload.items)
        if total_characters > self.settings.max_bulk_text_total_characters:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Bulk request exceeds the configured maximum combined content size of "
                    f"{self.settings.max_bulk_text_total_characters} characters"
                ),
            )

    def _validate_bulk_review_targets(
        self,
        snapshots: list[BulkItemSnapshot],
        entries_by_job_id: dict[str, object],
    ) -> None:
        allowed_job_ids = {snapshot.job_id for snapshot in snapshots if snapshot.job_id is not None}
        invalid_job_ids = [job_id for job_id in entries_by_job_id if job_id not in allowed_job_ids]
        if invalid_job_ids:
            invalid_label = ", ".join(invalid_job_ids)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Bulk review entries must reference jobs in this bulk run: {invalid_label}",
            )

    def _validate_bulk_transform_targets(
        self,
        snapshots: list[BulkItemSnapshot],
        overrides_by_job_id: dict[str, object],
    ) -> None:
        allowed_job_ids = {snapshot.job_id for snapshot in snapshots if snapshot.job_id is not None}
        invalid_job_ids = [
            job_id for job_id in overrides_by_job_id if job_id not in allowed_job_ids
        ]
        if invalid_job_ids:
            invalid_label = ", ".join(invalid_job_ids)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Bulk transform overrides must reference jobs in this bulk run: {invalid_label}",
            )

    def _error_message(self, exc: HTTPException) -> str:
        return exc.detail if isinstance(exc.detail, str) else "Bulk operation failed"
