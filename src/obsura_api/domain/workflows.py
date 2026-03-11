"""Workflow request and response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.common import BoundingBox, UuidReference
from obsura_api.domain.enums import ContentType, FindingKind, FindingSource, ReviewDecision
from obsura_api.domain.transforms import TransformationRule


class ManualTextSpan(BaseModel):
    """A manually selected range in text."""

    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content: str = Field(min_length=1)
    content_type: ContentType = ContentType.TEXT
    apply_builtins: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    exact_values: list[str] = Field(default_factory=list)
    manual_spans: list[ManualTextSpan] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    persist_job: bool = True
    persist_source_content: bool | None = None

    @model_validator(mode="after")
    def validate_content_type(self) -> "TextAnalysisRequest":
        if self.content_type not in {ContentType.TEXT, ContentType.STRUCTURED_TEXT}:
            raise ValueError("Text workflows only support `text` and `structured_text` content")
        return self


class TextAnalysisResponse(BaseModel):
    """Detection result for text workflows."""

    job_id: str | None = None
    findings: list[FindingRecord]
    summary: dict[str, int]


class FindingOverride(BaseModel):
    """Override a stored or transient finding before transformation."""

    model_config = ConfigDict(extra="forbid")

    finding_id: UuidReference | None = None
    start_index: int | None = None
    end_index: int | None = None
    decision: ReviewDecision | None = None
    transformation: TransformationRule | None = None

    @model_validator(mode="after")
    def validate_override(self) -> "FindingOverride":
        if self.finding_id is None and self.start_index is None and self.end_index is None:
            raise ValueError("A finding override must target a stored finding or a text span")
        if self.start_index is not None and self.end_index is not None and self.end_index <= self.start_index:
            raise ValueError("`end_index` must be greater than `start_index`")
        if self.decision is None and self.transformation is None:
            raise ValueError("A finding override must change the decision or transformation")
        return self


class TextTransformRequest(BaseModel):
    """Request to transform text from findings."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    job_id: UuidReference | None = None
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

    model_config = ConfigDict(extra="forbid")

    kind: FindingKind = FindingKind.IMAGE_REGION
    source: FindingSource = FindingSource.MANUAL
    entity_type: str = "IMAGE_REGION"
    entity_name: str | None = None
    region: BoundingBox
    transformation: TransformationRule | None = None
    metadata: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_kind(self) -> "ImageRegionInput":
        if self.kind not in {
            FindingKind.IMAGE_REGION,
            FindingKind.FACE_REGION,
            FindingKind.FACE_SUBREGION,
        }:
            raise ValueError("Image workflow regions cannot use the `text_span` finding kind")
        return self


class ImageWorkflowManifest(BaseModel):
    """Non-file image workflow inputs."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content_type: ContentType = ContentType.IMAGE
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    exact_values: list[str] = Field(default_factory=list)
    apply_builtins: bool = True
    regions: list[ImageRegionInput] = Field(default_factory=list)
    detect_text: bool = False
    detect_faces: bool = False
    default_transformation: TransformationRule | None = None
    persist_job: bool = True
    persist_source_content: bool | None = None

    @model_validator(mode="after")
    def validate_content_type(self) -> "ImageWorkflowManifest":
        if self.content_type not in {ContentType.IMAGE, ContentType.SCREENSHOT}:
            raise ValueError("Image workflows only support `image` and `screenshot` content")
        return self


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

    model_config = ConfigDict(extra="forbid")

    finding_id: UuidReference
    decision: ReviewDecision | None = None
    transformation: TransformationRule | None = None

    @model_validator(mode="after")
    def validate_override(self) -> "ImageFindingOverride":
        if self.decision is None and self.transformation is None:
            raise ValueError("An image finding override must change the decision or transformation")
        return self


class ImageJobTransformRequest(BaseModel):
    """Request to transform a persisted image job after review."""

    model_config = ConfigDict(extra="forbid")

    job_id: UuidReference
    finding_overrides: list[ImageFindingOverride] = Field(default_factory=list)
    include_pending: bool = False
    persist_output: bool = True
