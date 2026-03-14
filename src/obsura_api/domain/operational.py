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


class ServiceVersionInfo(BaseModel):
    """Runtime version and capability metadata."""

    name: str
    version: str
    environment: str
    database_backend: str
    schema_revision: str
    schema_head: str
    ocr_backend: str
    face_detector_backend: str
    ocr_available: bool
    face_detection_available: bool
