"""Operational metadata response models."""

from __future__ import annotations

from pydantic import BaseModel


class ServiceRootInfo(BaseModel):
    """Friendly API root metadata."""

    name: str
    status: str
    docs_url: str | None = None
    openapi_url: str | None = None
    version: str
    ocr_available: bool
    face_detection_available: bool
    pii_available: bool


class ServiceVersionInfo(BaseModel):
    """Runtime version and capability metadata."""

    name: str
    version: str
    environment: str
    database_backend: str
    schema_revision: str
    schema_head: str
    document_extractor_backend: str
    document_pdf_available: bool
    document_max_pages: int
    document_max_extracted_characters: int
    ocr_backend: str
    face_detector_backend: str
    pii_backend: str
    text_anonymizer_backend: str
    pii_languages: list[str]
    pii_custom_recognizers: bool
    text_hash_supported: bool
    share_output_intents: list[str]
    ocr_available: bool
    face_detection_available: bool
    pii_available: bool
