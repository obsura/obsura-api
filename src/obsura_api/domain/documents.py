"""PDF document workflow request and response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.common import UuidReference
from obsura_api.domain.enums import ContentType, OutputIntent
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.sharing import ShareArtifactSummary, SharePolicySummary
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride, FindingRecord


class DocumentWorkflowManifest(BaseModel):
    """Non-file inputs for PDF document analysis and transform workflows."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content_type: ContentType = ContentType.DOCUMENT
    apply_builtins: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    pii_detection: PIIDetectionOptions | None = None
    exact_values: list[str] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    output_intent: OutputIntent = OutputIntent.PREVIEW
    persist_job: bool = True

    @model_validator(mode="after")
    def validate_content_type(self) -> "DocumentWorkflowManifest":
        if self.content_type is not ContentType.DOCUMENT:
            raise ValueError("Document workflows only support `document` content")
        return self


class DocumentPageResult(BaseModel):
    """One page in an extracted or transformed PDF response."""

    page_number: int = Field(ge=1)
    character_count: int = Field(ge=0)
    output_text: str | None = None
    replacement_count: int = Field(default=0, ge=0)


class DocumentReplacementRecord(BaseModel):
    """One replacement applied to extracted PDF text."""

    entity_type: str
    page_number: int = Field(ge=1)
    start_index: int | None = None
    end_index: int | None = None
    original_preview: str | None = None
    output_value: str


class DocumentWorkflowResponse(BaseModel):
    """Review-first PDF workflow response."""

    job_id: str | None = None
    findings: list[FindingRecord]
    page_count: int = Field(ge=0)
    extracted_character_count: int = Field(ge=0)
    pages: list[DocumentPageResult] = Field(default_factory=list)
    output_text: str | None = None
    replacements: list[DocumentReplacementRecord] = Field(default_factory=list)
    output_intent: OutputIntent | None = None
    share_policy: SharePolicySummary | None = None
    artifacts: list[ShareArtifactSummary] = Field(default_factory=list)
    summary: dict[str, int]


class DocumentJobTransformRequest(BaseModel):
    """Request to transform a reviewed PDF job using a resubmitted file."""

    model_config = ConfigDict(extra="forbid")

    job_id: UuidReference
    finding_overrides: list[FindingOverride] = Field(default_factory=list)
    include_pending: bool = False
    default_transformation: TransformationRule | None = None
    output_intent: OutputIntent = OutputIntent.PREVIEW
    persist_output: bool = True
