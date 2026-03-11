"""Transformation request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from obsura_api.domain.enums import TransformationMode


class TransformationRule(BaseModel):
    """How a finding should be transformed for output."""

    mode: TransformationMode = TransformationMode.GENERIC
    placeholder: str | None = None
    semantic_label: str | None = None
    alias_prefix: str | None = None
    prefix_visible: int = Field(default=0, ge=0)
    suffix_visible: int = Field(default=0, ge=0)
    mask_character: str = "*"
    blur_radius: int = Field(default=8, ge=1)
    pixelation_scale: int = Field(default=8, ge=2)
    overlay_color: str = "#111111"
    overlay_label: str | None = None

    @model_validator(mode="after")
    def validate_mode_settings(self) -> "TransformationRule":
        if self.mode in {
            TransformationMode.CUSTOM,
            TransformationMode.GENERIC,
        } and not self.placeholder:
            self.placeholder = "[REDACTED]"

        if self.mode is TransformationMode.SEMANTIC and not self.semantic_label:
            self.semantic_label = "SENSITIVE_VALUE"

        return self

