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
    REDACT = "redact"
    HASH = "hash"
    BLUR = "blur"
    PIXELATE = "pixelate"
    OVERLAY = "overlay"
    IMAGE_REPLACEMENT = "image_replacement"


class OverlayShape(str, Enum):
    RECTANGLE = "rectangle"
    ROUNDED_RECTANGLE = "rounded_rectangle"
    ELLIPSE = "ellipse"


class LabelPosition(str, Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"
    OUTSIDE_TOP = "outside_top"
    OUTSIDE_BOTTOM = "outside_bottom"


class LabelFontFamily(str, Enum):
    SANS = "sans"
    SERIF = "serif"
    MONO = "mono"


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


class BulkJobStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    PARTIALLY_REVIEWED = "partially_reviewed"
    REVIEWED = "reviewed"
    PARTIALLY_TRANSFORMED = "partially_transformed"
    TRANSFORMED = "transformed"


class BulkJobItemStatus(str, Enum):
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    REVIEWED = "reviewed"
    TRANSFORMED = "transformed"


class BulkOperationKind(str, Enum):
    REVIEW = "review"
    TRANSFORM = "transform"


class BulkOperationItemStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class SearchResultKind(str, Enum):
    PATTERN = "pattern"
    CUSTOM_ENTITY = "custom_entity"
    CONFIGURATION = "configuration"
    JOB = "job"
