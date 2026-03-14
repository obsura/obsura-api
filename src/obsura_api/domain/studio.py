"""Studio asset request and response models."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from obsura_api.domain.common import TimestampedModel, UuidReference
from obsura_api.domain.enums import ConfigurationKind, ContentType, MatcherKind
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.transforms import TransformationRule


class PatternMatcherDefinition(BaseModel):
    """One custom detection rule."""

    model_config = ConfigDict(extra="forbid")

    kind: MatcherKind
    value: str | None = None
    values: list[str] = Field(default_factory=list)
    case_sensitive: bool = False
    applies_to: list[ContentType] = Field(
        default_factory=lambda: [ContentType.TEXT, ContentType.STRUCTURED_TEXT],
    )

    @model_validator(mode="after")
    def validate_payload(self) -> "PatternMatcherDefinition":
        if self.kind in {MatcherKind.EXACT, MatcherKind.REGEX} and not self.value:
            raise ValueError("`value` is required for exact and regex matchers")
        if self.kind is MatcherKind.VALUE_LIST and not self.values:
            raise ValueError("`values` is required for value-list matchers")
        if self.kind is MatcherKind.REGEX and self.value:
            try:
                re.compile(self.value)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {exc}") from exc
        return self


class PatternBase(BaseModel):
    """Shared fields for saved patterns."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    matcher: PatternMatcherDefinition
    transformation: TransformationRule | None = None
    scope: dict[str, str] = Field(default_factory=dict)


class PatternCreate(PatternBase):
    """Payload for creating a pattern."""


class PatternUpdate(BaseModel):
    """Partial update for a pattern."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None
    matcher: PatternMatcherDefinition | None = None
    transformation: TransformationRule | None = None
    scope: dict[str, str] | None = None


class PatternRead(TimestampedModel, PatternBase):
    """Stored pattern representation."""


class CustomEntityBase(BaseModel):
    """Shared fields for saved custom entities."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    detection_definitions: list[PatternMatcherDefinition] = Field(default_factory=list)
    transformation: TransformationRule | None = None
    scope: dict[str, str] = Field(default_factory=dict)


class CustomEntityCreate(CustomEntityBase):
    """Payload for creating a custom entity."""


class CustomEntityUpdate(BaseModel):
    """Partial update for a custom entity."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None
    detection_definitions: list[PatternMatcherDefinition] | None = None
    transformation: TransformationRule | None = None
    scope: dict[str, str] | None = None


class CustomEntityRead(TimestampedModel, CustomEntityBase):
    """Stored custom entity representation."""


class ConfigurationBase(BaseModel):
    """Shared fields for packs, profiles, and presets."""

    model_config = ConfigDict(extra="forbid")

    kind: ConfigurationKind
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    pattern_ids: list[UuidReference] = Field(default_factory=list)
    custom_entity_ids: list[UuidReference] = Field(default_factory=list)
    default_text_transformation: TransformationRule | None = None
    default_image_transformation: TransformationRule | None = None
    pii_detection: PIIDetectionOptions | None = None
    face_preferences: dict[str, str | int | bool] = Field(default_factory=dict)
    metadata: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)


class ConfigurationCreate(ConfigurationBase):
    """Payload for creating a configuration asset."""


class ConfigurationUpdate(BaseModel):
    """Partial update for a configuration asset."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None
    pattern_ids: list[UuidReference] | None = None
    custom_entity_ids: list[UuidReference] | None = None
    default_text_transformation: TransformationRule | None = None
    default_image_transformation: TransformationRule | None = None
    pii_detection: PIIDetectionOptions | None = None
    face_preferences: dict[str, str | int | bool] | None = None
    metadata: dict[str, str | int | bool | list[str]] | None = None


class ConfigurationRead(TimestampedModel, ConfigurationBase):
    """Stored pack, profile, or preset."""


class PatternFromSelectionRequest(BaseModel):
    """Create a reusable pattern from a selected exact value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    selected_value: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    transformation: TransformationRule | None = None
    applies_to: list[ContentType] = Field(
        default_factory=lambda: [ContentType.TEXT, ContentType.STRUCTURED_TEXT],
    )
