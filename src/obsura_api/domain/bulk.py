"""Bulk text request and response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.common import TimestampedModel, UuidReference
from obsura_api.domain.enums import (
    BulkJobItemStatus,
    BulkJobStatus,
    BulkOperationItemStatus,
    BulkOperationKind,
    ContentType,
    JobStatus,
)
from obsura_api.domain.jobs import JobReviewDecisionInput
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride


class BulkTextAnalyzeItemInput(BaseModel):
    """One submitted text item inside a bulk analyze request."""

    model_config = ConfigDict(extra="forbid")

    client_item_id: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=160)
    content: str | None = None


class BulkTextAnalyzeRequest(BaseModel):
    """Bulk text analyze request with shared options and ordered items."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=160)
    content_type: ContentType = ContentType.TEXT
    apply_builtins: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    pii_detection: PIIDetectionOptions | None = None
    exact_values: list[str] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    persist_source_content: bool | None = None
    items: list[BulkTextAnalyzeItemInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> "BulkTextAnalyzeRequest":
        if self.content_type not in {ContentType.TEXT, ContentType.STRUCTURED_TEXT}:
            raise ValueError(
                "Bulk text workflows only support `text` and `structured_text` content"
            )

        seen_client_ids: set[str] = set()
        for item in self.items:
            if item.client_item_id is None:
                continue
            normalized = item.client_item_id.strip()
            if not normalized:
                raise ValueError("`client_item_id` must not be blank when provided")
            if normalized in seen_client_ids:
                raise ValueError(f"Duplicate `client_item_id` value: {normalized}")
            seen_client_ids.add(normalized)
            item.client_item_id = normalized
        return self


class BulkJobItemRead(BaseModel):
    """One stored per-item result inside a bulk job."""

    id: str
    item_index: int
    client_item_id: str | None = None
    title: str | None = None
    status: BulkJobItemStatus
    job_id: str | None = None
    job_status: JobStatus | None = None
    error: str | None = None
    summary: dict[str, int] = Field(
        default_factory=dict,
        description="Finding decision summary for the child job using the standard total/pending/approved/rejected shape.",
    )
    output_count: int = Field(default=0, description="Stored output count for the child job.")
    output_available: bool = Field(
        default=False,
        description="Whether the child job currently has at least one stored output.",
    )


class BulkJobSummaryRead(TimestampedModel):
    """List/detail summary for a persisted bulk job."""

    title: str | None = None
    content_type: ContentType
    status: BulkJobStatus
    item_count: int = Field(description="Number of submitted items in the bulk run.")
    success_count: int = Field(
        description="Number of items that produced persisted child jobs during bulk analyze.",
    )
    failure_count: int = Field(
        description="Number of items that failed during bulk analyze and did not produce child jobs.",
    )


class BulkJobRead(BulkJobSummaryRead):
    """Detailed persisted bulk job with ordered per-item results."""

    reviewed_item_count: int = Field(
        default=0,
        description="Number of child jobs that currently have reviewed findings.",
    )
    transformed_item_count: int = Field(
        default=0,
        description="Number of child jobs with at least one persisted text output.",
    )
    output_count: int = Field(
        default=0,
        description="Total number of stored outputs across all child jobs in this bulk run.",
    )
    items: list[BulkJobItemRead] = Field(default_factory=list)


class BulkJobReviewEntry(BaseModel):
    """Review decisions targeting one child job inside a bulk run."""

    model_config = ConfigDict(extra="forbid")

    job_id: UuidReference
    decisions: list[JobReviewDecisionInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decisions(self) -> "BulkJobReviewEntry":
        finding_ids = [decision.finding_id for decision in self.decisions]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("Each bulk review entry must reference each finding only once")
        return self


class BulkJobReviewRequest(BaseModel):
    """Bulk review request for one persisted bulk run."""

    model_config = ConfigDict(extra="forbid")

    jobs: list[BulkJobReviewEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_jobs(self) -> "BulkJobReviewRequest":
        job_ids = [item.job_id for item in self.jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("Bulk review payload must not contain duplicate job entries")
        return self


class BulkTextTransformOverride(BaseModel):
    """Optional override for transforming one child job inside a bulk run."""

    model_config = ConfigDict(extra="forbid")

    job_id: UuidReference
    content: str | None = None
    finding_overrides: list[FindingOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_overrides(self) -> "BulkTextTransformOverride":
        finding_ids = [
            override.finding_id for override in self.finding_overrides if override.finding_id
        ]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError(
                "Bulk transform overrides must not target the same finding more than once"
            )
        return self


class BulkTextTransformRequest(BaseModel):
    """Bulk text transform request for a persisted bulk run."""

    model_config = ConfigDict(extra="forbid")

    bulk_id: UuidReference
    job_overrides: list[BulkTextTransformOverride] = Field(default_factory=list)
    include_pending: bool = False
    default_transformation: TransformationRule | None = None
    persist_output: bool = True

    @model_validator(mode="after")
    def validate_overrides(self) -> "BulkTextTransformRequest":
        job_ids = [item.job_id for item in self.job_overrides]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("Bulk transform payload must not contain duplicate job overrides")
        return self


class BulkOperationItemResult(BaseModel):
    """Per-item result for a bulk review or transform action."""

    id: str
    item_index: int
    client_item_id: str | None = None
    title: str | None = None
    job_id: str | None = None
    operation_status: BulkOperationItemStatus
    bulk_item_status: BulkJobItemStatus
    job_status: JobStatus | None = None
    error: str | None = None
    summary: dict[str, int] = Field(
        default_factory=dict,
        description="Finding decision summary for the current child job state.",
    )
    output_count: int = Field(default=0, description="Stored output count for the child job.")
    output_available: bool = Field(
        default=False,
        description="Whether the child job currently has at least one stored output.",
    )


class BulkReviewItemResult(BulkOperationItemResult):
    """Per-item result for bulk review."""

    decision_count: int = 0


class BulkTextTransformItemResult(BulkOperationItemResult):
    """Per-item result for bulk transform."""

    replacement_count: int = 0
    output_text: str | None = None


class BulkOperationResponse(BaseModel):
    """Shared bulk action response envelope payload."""

    bulk_id: str
    action: BulkOperationKind
    status: BulkJobStatus
    item_count: int = Field(description="Total items in the targeted bulk run.")
    success_count: int = Field(description="Items successfully processed by this action.")
    failure_count: int = Field(description="Items that failed during this action.")
    skipped_count: int = Field(description="Items intentionally left untouched by this action.")
    reviewed_item_count: int = Field(
        default=0,
        description="Current reviewed child job count after this action completes.",
    )
    transformed_item_count: int = Field(
        default=0,
        description="Current transformed child job count after this action completes.",
    )
    output_count: int = Field(
        default=0,
        description="Current stored output count across the bulk run after this action completes.",
    )


class BulkReviewResponse(BulkOperationResponse):
    """Bulk review response."""

    items: list[BulkReviewItemResult] = Field(default_factory=list)


class BulkTextTransformResponse(BulkOperationResponse):
    """Bulk text transform response."""

    items: list[BulkTextTransformItemResult] = Field(default_factory=list)
