"""Shared domain enums for Obsura API."""

from __future__ import annotations

from enum import Enum


class ContentType(str, Enum):
    TEXT = "text"
    STRUCTURED_TEXT = "structured_text"
    SCREENSHOT = "screenshot"
    IMAGE = "image"


class MatcherKind(str, Enum):
    EXACT = "exact"
    REGEX = "regex"
    VALUE_LIST = "value_list"


class ConfigurationKind(str, Enum):
    PACK = "pack"
    PROFILE = "profile"
    PRESET = "preset"


class TransformationMode(str, Enum):
    GENERIC = "generic"
    SEMANTIC = "semantic"
    CUSTOM = "custom"
    PARTIAL_MASK = "partial_mask"
    STABLE_ALIAS = "stable_alias"
    MASK = "mask"
    BLUR = "blur"
    PIXELATE = "pixelate"
    OVERLAY = "overlay"
    IMAGE_REPLACEMENT = "image_replacement"


class FindingSource(str, Enum):
    BUILT_IN = "built_in"
    CUSTOM = "custom"
    MANUAL = "manual"
    FACE = "face"
    OCR = "ocr"


class FindingKind(str, Enum):
    TEXT_SPAN = "text_span"
    IMAGE_REGION = "image_region"
    FACE_REGION = "face_region"
    FACE_SUBREGION = "face_subregion"


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobStatus(str, Enum):
    ANALYZED = "analyzed"
    REVIEWED = "reviewed"
    TRANSFORMED = "transformed"


class SearchResultKind(str, Enum):
    PATTERN = "pattern"
    CUSTOM_ENTITY = "custom_entity"
    CONFIGURATION = "configuration"
    JOB = "job"

