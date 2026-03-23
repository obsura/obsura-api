"""PII detection request models and merge helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIDENCE_PROFILE_THRESHOLDS: dict[str, float] = {
    "strict": 0.9,
    "balanced": 0.8,
    "aggressive": 0.7,
}


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _normalize_threshold(value: float | int | str) -> float:
    if isinstance(value, str):
        parsed = value.strip().rstrip("%")
        if not parsed:
            raise ValueError("Confidence threshold must not be blank")
        raw = float(parsed)
    else:
        raw = float(value)
    if raw > 1.0:
        raw = raw / 100.0
    return raw


class PIIDetectionOptions(BaseModel):
    """Per-request or per-configuration PII detection tuning."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, min_length=2, max_length=16)
    entity_allow_list: list[str] = Field(default_factory=list)
    context_words: list[str] = Field(default_factory=list)
    confidence_profile: str | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    entity_min_confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("entity_allow_list")
    @classmethod
    def normalize_entity_allow_list(cls, values: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in values if item and item.strip()]
        return _unique_preserve_order(normalized)

    @field_validator("context_words")
    @classmethod
    def normalize_context_words(cls, values: list[str]) -> list[str]:
        normalized = [item.strip() for item in values if item and item.strip()]
        return _unique_preserve_order(normalized)

    @field_validator("confidence_profile")
    @classmethod
    def normalize_confidence_profile(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in CONFIDENCE_PROFILE_THRESHOLDS:
            allowed = ", ".join(sorted(CONFIDENCE_PROFILE_THRESHOLDS))
            raise ValueError(f"Unsupported confidence profile `{normalized}`. Allowed: {allowed}")
        return normalized

    @field_validator("min_confidence", mode="before")
    @classmethod
    def normalize_min_confidence(cls, value: float | int | str | None) -> float | None:
        if value is None:
            return None
        return _normalize_threshold(value)

    @field_validator("entity_min_confidence", mode="before")
    @classmethod
    def normalize_entity_min_confidence(
        cls,
        value: dict[str, float | int | str] | None,
    ) -> dict[str, float]:
        if value is None:
            return {}
        normalized: dict[str, float] = {}
        for entity_type, threshold in value.items():
            if not entity_type or not entity_type.strip():
                continue
            normalized[entity_type.strip().upper()] = _normalize_threshold(threshold)
        return normalized

    def resolved_min_confidence(self, entity_type: str | None = None) -> float | None:
        """Resolve confidence threshold with precedence entity > explicit > profile."""

        profile_threshold = None
        if self.confidence_profile is not None:
            profile_threshold = CONFIDENCE_PROFILE_THRESHOLDS[self.confidence_profile]

        explicit_threshold = self.min_confidence
        if explicit_threshold is None:
            explicit_threshold = profile_threshold
        elif profile_threshold is not None:
            explicit_threshold = max(explicit_threshold, profile_threshold)

        if entity_type is None:
            return explicit_threshold

        per_entity = self.entity_min_confidence.get(entity_type.upper())
        if per_entity is None:
            return explicit_threshold
        if explicit_threshold is None:
            return per_entity
        return max(per_entity, explicit_threshold)


def merge_pii_detection_options(
    *options: PIIDetectionOptions | None,
) -> PIIDetectionOptions | None:
    """Merge ordered options using least-privilege entity filtering."""

    active = [item for item in options if item is not None]
    if not active:
        return None

    language = next((item.language for item in reversed(active) if item.language), None)
    confidence_profile = next(
        (item.confidence_profile for item in reversed(active) if item.confidence_profile),
        None,
    )
    context_words = _unique_preserve_order(
        [word for item in active for word in item.context_words],
    )

    scoped_allow_lists = [item.entity_allow_list for item in active if item.entity_allow_list]
    entity_allow_list: list[str] = []
    if scoped_allow_lists:
        allowed = set(scoped_allow_lists[0])
        for values in scoped_allow_lists[1:]:
            allowed &= set(values)
        entity_allow_list = [item for item in scoped_allow_lists[0] if item in allowed]

    min_confidence = max(
        (item.min_confidence for item in active if item.min_confidence is not None),
        default=None,
    )

    entity_min_confidence: dict[str, float] = {}
    for item in active:
        for entity_type, threshold in item.entity_min_confidence.items():
            current = entity_min_confidence.get(entity_type)
            entity_min_confidence[entity_type] = (
                threshold if current is None else max(current, threshold)
            )

    merged = PIIDetectionOptions(
        language=language,
        entity_allow_list=entity_allow_list,
        context_words=context_words,
        confidence_profile=confidence_profile,
        min_confidence=min_confidence,
        entity_min_confidence=entity_min_confidence,
    )
    if not (
        merged.language
        or merged.entity_allow_list
        or merged.context_words
        or merged.confidence_profile
        or merged.min_confidence is not None
        or merged.entity_min_confidence
    ):
        return None
    return merged
