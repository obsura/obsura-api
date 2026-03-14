"""Transformation request and response models."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.enums import LabelFontFamily, LabelPosition, OverlayShape, TransformationMode

HEX_COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}")


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
    region_padding: int = Field(default=0, ge=0)
    overlay_shape: OverlayShape = OverlayShape.RECTANGLE
    overlay_corner_radius: int = Field(default=12, ge=0)
    outline_color: str | None = None
    outline_width: int = Field(default=0, ge=0)
    label_color: str = "#FFFFFF"
    label_background_color: str | None = None
    label_position: LabelPosition = LabelPosition.TOP_LEFT
    label_font_family: LabelFontFamily = LabelFontFamily.SANS
    label_font_size: int = Field(default=14, ge=8, le=96)
    label_padding: int = Field(default=4, ge=0)
    label_margin: int = Field(default=4, ge=0)

    @model_validator(mode="after")
    def validate_mode_settings(self) -> "TransformationRule":
        if len(self.mask_character) != 1:
            raise ValueError("`mask_character` must be a single character")
        if not HEX_COLOR_PATTERN.fullmatch(self.overlay_color):
            raise ValueError("`overlay_color` must be a hex color like `#111111`")
        if self.outline_color is not None and not HEX_COLOR_PATTERN.fullmatch(self.outline_color):
            raise ValueError("`outline_color` must be a hex color like `#111111`")
        if not HEX_COLOR_PATTERN.fullmatch(self.label_color):
            raise ValueError("`label_color` must be a hex color like `#FFFFFF`")
        if self.label_background_color is not None and not HEX_COLOR_PATTERN.fullmatch(
            self.label_background_color
        ):
            raise ValueError("`label_background_color` must be a hex color like `#111111`")

        if (
            self.mode
            in {
                TransformationMode.CUSTOM,
                TransformationMode.GENERIC,
            }
            and not self.placeholder
        ):
            self.placeholder = "[REDACTED]"

        if self.mode is TransformationMode.SEMANTIC and not self.semantic_label:
            self.semantic_label = "SENSITIVE_VALUE"

        return self
