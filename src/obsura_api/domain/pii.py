"""PII detection request models and merge helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class PIIDetectionOptions(BaseModel):
    """Per-request or per-configuration PII detection tuning."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, min_length=2, max_length=16)
    entity_allow_list: list[str] = Field(default_factory=list)
    context_words: list[str] = Field(default_factory=list)

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


def merge_pii_detection_options(
    *options: PIIDetectionOptions | None,
) -> PIIDetectionOptions | None:
    """Merge ordered options using least-privilege entity filtering."""

    active = [item for item in options if item is not None]
    if not active:
        return None

    language = next((item.language for item in reversed(active) if item.language), None)
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

    merged = PIIDetectionOptions(
        language=language,
        entity_allow_list=entity_allow_list,
        context_words=context_words,
    )
    if not (merged.language or merged.entity_allow_list or merged.context_words):
        return None
    return merged
