"""Job history request and response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from obsura_api.domain.common import TimestampedModel, UuidReference
from obsura_api.domain.enums import ContentType, JobStatus, ReviewDecision
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord


class JobOutputRecord(TimestampedModel):
    """A stored output generated from a job."""

    job_id: str
    content_type: ContentType
    output_text: str | None = None
    output_file_path: str | None = None
    media_url: str | None = None
    metadata: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)


class JobRead(TimestampedModel):
    """Full stored job representation."""

    title: str | None = None
    status: JobStatus
    content_type: ContentType
    source_text: str | None = None
    source_file_path: str | None = None
    pattern_ids: list[str] = Field(default_factory=list)
    custom_entity_ids: list[str] = Field(default_factory=list)
    configuration_ids: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    findings: list[FindingRecord] = Field(default_factory=list)
    outputs: list[JobOutputRecord] = Field(default_factory=list)


class JobReviewDecisionInput(BaseModel):
    """Review decision for a single finding."""

    model_config = ConfigDict(extra="forbid")

    finding_id: UuidReference
    decision: ReviewDecision
    transformation: TransformationRule | None = None


class JobReviewRequest(BaseModel):
    """Batch review update for stored findings."""

    model_config = ConfigDict(extra="forbid")

    decisions: list[JobReviewDecisionInput] = Field(min_length=1)
