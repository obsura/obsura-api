"""Transformation request and response models."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.enums import TransformationMode


class TransformationRule(BaseModel):
    """How a finding should be transformed for output."""

    model_config = ConfigDict(extra="forbid")

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
        if len(self.mask_character) != 1:
            raise ValueError("`mask_character` must be a single character")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}", self.overlay_color):
            raise ValueError("`overlay_color` must be a hex color like `#111111`")

        if self.mode in {
            TransformationMode.CUSTOM,
            TransformationMode.GENERIC,
        } and not self.placeholder:
            self.placeholder = "[REDACTED]"

        if self.mode is TransformationMode.SEMANTIC and not self.semantic_label:
            self.semantic_label = "SENSITIVE_VALUE"

        return self
