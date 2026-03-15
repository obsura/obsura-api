"""Structured JSON workflow request and response models."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.common import UuidReference
from obsura_api.domain.enums import OutputIntent
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.sharing import SharePolicySummary
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride, FindingRecord

StructuredJSONValue = dict[str, Any] | list[Any]


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Structured JSON values must not contain NaN or Infinity")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Structured JSON object keys must be strings")
            _validate_json_value(item)
        return
    raise ValueError("Structured workflows only support JSON-compatible objects and arrays")


class StructuredAnalysisRequest(BaseModel):
    """Request to analyze structured JSON content."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    data: StructuredJSONValue
    apply_builtins: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    pii_detection: PIIDetectionOptions | None = None
    exact_values: list[str] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    output_intent: OutputIntent = OutputIntent.PREVIEW
    persist_job: bool = True
    persist_source_content: bool | None = None

    @model_validator(mode="after")
    def validate_data(self) -> "StructuredAnalysisRequest":
        _validate_json_value(self.data)
        return self


class StructuredTransformRequest(BaseModel):
    """Request to analyze and transform structured JSON content in one call."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    data: StructuredJSONValue
    apply_builtins: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    configuration_ids: list[UuidReference] = Field(default_factory=list)
    pii_detection: PIIDetectionOptions | None = None
    exact_values: list[str] = Field(default_factory=list)
    default_transformation: TransformationRule | None = None
    output_intent: OutputIntent = OutputIntent.PREVIEW
    persist_job: bool = True
    persist_source_content: bool | None = None
    persist_output: bool = True

    @model_validator(mode="after")
    def validate_data(self) -> "StructuredTransformRequest":
        _validate_json_value(self.data)
        return self


class StructuredReplacementRecord(BaseModel):
    """One structured-field replacement in a transformed output."""

    entity_type: str
    path: str
    start_index: int | None = None
    end_index: int | None = None
    original_preview: str | None = None
    output_value: str


class StructuredWorkflowResponse(BaseModel):
    """Structured workflow result for analyze or transform operations."""

    job_id: str | None = None
    findings: list[FindingRecord]
    output_data: StructuredJSONValue | None = None
    replacements: list[StructuredReplacementRecord] = Field(default_factory=list)
    output_intent: OutputIntent | None = None
    share_policy: SharePolicySummary | None = None
    summary: dict[str, int]


class StructuredJobTransformRequest(BaseModel):
    """Request to transform a persisted structured job after review decisions."""

    model_config = ConfigDict(extra="forbid")

    job_id: UuidReference
    data: StructuredJSONValue
    finding_overrides: list[FindingOverride] = Field(default_factory=list)
    include_pending: bool = False
    default_transformation: TransformationRule | None = None
    output_intent: OutputIntent = OutputIntent.PREVIEW
    persist_output: bool = True

    @model_validator(mode="after")
    def validate_data(self) -> "StructuredJobTransformRequest":
        _validate_json_value(self.data)
        return self
