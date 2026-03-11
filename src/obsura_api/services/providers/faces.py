"""Face detection provider contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from obsura_api.domain.common import BoundingBox


@dataclass(slots=True)
class DetectedFaceRegion:
    """One face or face subregion returned by a detection provider."""

    region: BoundingBox
    subregions: dict[str, BoundingBox] = field(default_factory=dict)
    confidence: float = 1.0


class FaceDetector(Protocol):
    """Protocol for automatic face detection backends."""

    name: str
    supported: bool

    def detect_faces(self, image_bytes: bytes) -> list[DetectedFaceRegion]:
        """Detect faces in the provided image."""


class NoOpFaceDetector:
    """Default face detector that makes lack of provider support explicit."""

    name = "noop-face-detector"
    supported = False

    def detect_faces(self, image_bytes: bytes) -> list[DetectedFaceRegion]:
        return []

