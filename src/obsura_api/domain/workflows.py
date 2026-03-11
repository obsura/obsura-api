"""Workflow request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from obsura_api.domain.common import BoundingBox
from obsura_api.domain.enums import ContentType, FindingKind, FindingSource, ReviewDecision
from obsura_api.domain.transforms import TransformationRule


class ManualTextSpan(BaseModel):
    """A manually selected range in text."""

    start_index: int = Field(ge=0)
    end_index: int = Field(gt=0)
    entity_type: str = "MANUAL_SELECTION"
    entity_name: str | None = None
    transformation: TransformationRule | None = None

    @model_validator(mode="after")
    def validate_span(self) -> "ManualTextSpan":
        if self.end_index <= self.start_index:
            raise ValueError("`end_index` must be greater than `start_index`")
        return self


class FindingRecord(BaseModel):
    """Reviewable finding for text or image workflows."""

    id: str | None = None
    job_id: str | None = None
    source: FindingSource
    kind: FindingKind
    entity_type: str
    entity_name: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    region: BoundingBox | None = None
    matched_text_preview: str | None = None
    matched_text_hash: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    decision: ReviewDecision = ReviewDecision.PENDING
    transformation: TransformationRule | None = None
    metadata: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)


class TextAnalysisRequest(BaseModel):
    """Request to detect findings in text-like content."""

    title: str | None = None
    content: str
    content_type: ContentType = ContentType.TEXT
    apply_builtins: bool = True
    pattern_ids: list[str] = Field(default_factory=list)
    custom_entity_ids: list[str] = Field(default_factory=list)
    configuration_ids: list[str] = Field(default_factory=list)
    exact_values: list[str] = Field(default_factory=list)
    manual_spans: list[ManualTextSpan] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    persist_job: bool = True
    persist_source_content: bool | None = None


class TextAnalysisResponse(BaseModel):
    """Detection result for text workflows."""

    job_id: str | None = None
    findings: list[FindingRecord]
    summary: dict[str, int]


class FindingOverride(BaseModel):
    """Override a stored or transient finding before transformation."""

    finding_id: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    decision: ReviewDecision | None = None
    transformation: TransformationRule | None = None


class TextTransformRequest(BaseModel):
    """Request to transform text from findings."""

    content: str | None = None
    job_id: str | None = None
    finding_overrides: list[FindingOverride] = Field(default_factory=list)
    include_pending: bool = False
    default_transformation: TransformationRule | None = None
    persist_output: bool = True

    @model_validator(mode="after")
    def validate_payload(self) -> "TextTransformRequest":
        if not self.content and not self.job_id:
            raise ValueError("`content` or `job_id` is required")
        return self


class ReplacementRecord(BaseModel):
    """One applied replacement in a transformed output."""

    entity_type: str
    start_index: int | None = None
    end_index: int | None = None
    original_preview: str | None = None
    output_value: str


class TextTransformResponse(BaseModel):
    """Transformation result for text content."""

    job_id: str | None = None
    output_text: str
    replacements: list[ReplacementRecord]
    summary: dict[str, int]


class ImageRegionInput(BaseModel):
    """A region selected for image review or transformation."""

    kind: FindingKind = FindingKind.IMAGE_REGION
    source: FindingSource = FindingSource.MANUAL
    entity_type: str = "IMAGE_REGION"
    entity_name: str | None = None
    region: BoundingBox
    transformation: TransformationRule | None = None
    metadata: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)


class ImageWorkflowManifest(BaseModel):
    """Non-file image workflow inputs."""

    title: str | None = None
    content_type: ContentType = ContentType.IMAGE
    configuration_ids: list[str] = Field(default_factory=list)
    regions: list[ImageRegionInput] = Field(default_factory=list)
    detect_faces: bool = False
    persist_job: bool = True
    persist_source_content: bool | None = None


class ImageWorkflowResponse(BaseModel):
    """Response for image analysis or transformation."""

    job_id: str | None = None
    findings: list[FindingRecord]
    stored_input_path: str | None = None
    stored_output_path: str | None = None
    media_url: str | None = None
    summary: dict[str, int]


class ImageFindingOverride(BaseModel):
    """Override a stored image finding before export."""

    finding_id: str
    decision: ReviewDecision | None = None
    transformation: TransformationRule | None = None


class ImageJobTransformRequest(BaseModel):
    """Request to transform a persisted image job after review."""

    job_id: str
    finding_overrides: list[ImageFindingOverride] = Field(default_factory=list)
    include_pending: bool = False
    persist_output: bool = True
