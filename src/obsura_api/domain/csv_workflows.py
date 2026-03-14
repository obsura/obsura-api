"""CSV workflow request and response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.common import UuidReference
from obsura_api.domain.enums import ContentType
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride, FindingRecord

CSVDelimiter = Literal[",", ";", "\t"]


class CSVWorkflowManifest(BaseModel):
    """Non-file CSV workflow inputs."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content_type: ContentType = ContentType.CSV
    apply_builtins: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    pii_detection: PIIDetectionOptions | None = None
    exact_values: list[str] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    persist_job: bool = True
    has_header: bool = True
    delimiter: CSVDelimiter = ","
    quotechar: str = '"'

    @model_validator(mode="after")
    def validate_manifest(self) -> "CSVWorkflowManifest":
        if self.content_type is not ContentType.CSV:
            raise ValueError("CSV workflows only support `csv` content")
        if len(self.quotechar) != 1:
            raise ValueError("`quotechar` must be one character")
        return self


class CSVReplacementRecord(BaseModel):
    """One replacement applied inside a CSV cell."""

    entity_type: str
    row_number: int = Field(ge=1)
    column_index: int = Field(ge=1)
    column_name: str
    start_index: int | None = None
    end_index: int | None = None
    original_preview: str | None = None
    output_value: str


class CSVWorkflowResponse(BaseModel):
    """Review-first CSV workflow response."""

    job_id: str | None = None
    findings: list[FindingRecord]
    has_header: bool
    headers: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    output_rows: list[list[str]] | None = None
    output_csv: str | None = None
    formula_escape_count: int = Field(default=0, ge=0)
    replacements: list[CSVReplacementRecord] = Field(default_factory=list)
    summary: dict[str, int]


class CSVJobTransformRequest(BaseModel):
    """Request to transform a reviewed CSV job using a resubmitted file."""

    model_config = ConfigDict(extra="forbid")

    job_id: UuidReference
    finding_overrides: list[FindingOverride] = Field(default_factory=list)
    include_pending: bool = False
    default_transformation: TransformationRule | None = None
    persist_output: bool = True
