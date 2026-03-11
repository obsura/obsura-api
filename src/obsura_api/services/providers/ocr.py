"""OCR provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from obsura_api.domain.common import BoundingBox


@dataclass(slots=True)
class OCRBlock:
    """Text extracted from an image by an OCR engine."""

    text: str
    region: BoundingBox
    confidence: float


class OCRProvider(Protocol):
    """Protocol for OCR providers used by image workflows."""

    name: str

    def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
        """Return OCR text blocks from an image."""


class NoOpOCRProvider:
    """Default OCR provider used until a real engine is configured."""

    name = "noop-ocr"

    def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
        return []

