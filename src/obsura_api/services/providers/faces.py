"""Face detection provider contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from obsura_api.domain.common import BoundingBox

if TYPE_CHECKING:
    from obsura_api.core.settings import Settings


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


class OpenCVHaarFaceDetector:
    """OpenCV Haar-cascade based face detector with optional eye subregions."""

    name = "opencv-haar-face-detector"
    supported = True

    def __init__(self) -> None:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV face detection requires the `opencv-python-headless` package.",
            ) from exc

        self.cv2 = cv2
        self.np = np
        cascade_root = Path(cv2.data.haarcascades)
        self.face_cascade = cv2.CascadeClassifier(
            str(cascade_root / "haarcascade_frontalface_default.xml"),
        )
        self.eye_cascade = cv2.CascadeClassifier(str(cascade_root / "haarcascade_eye.xml"))

        if self.face_cascade.empty():
            raise RuntimeError("Failed to load the OpenCV frontal-face cascade classifier.")
        if self.eye_cascade.empty():
            self.eye_cascade = None

    def detect_faces(self, image_bytes: bytes) -> list[DetectedFaceRegion]:
        array = self.np.frombuffer(image_bytes, dtype=self.np.uint8)
        image = self.cv2.imdecode(array, self.cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unable to decode image bytes for face detection")

        grayscale = self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            grayscale,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(24, 24),
        )

        detected_regions: list[DetectedFaceRegion] = []
        for x, y, width, height in faces:
            face_box = BoundingBox(
                x=int(x),
                y=int(y),
                width=int(width),
                height=int(height),
            )
            subregions = self._detect_eye_regions(
                grayscale=grayscale,
                face_box=face_box,
            )
            detected_regions.append(
                DetectedFaceRegion(
                    region=face_box,
                    subregions=subregions,
                    confidence=1.0,
                ),
            )
        return detected_regions

    def _detect_eye_regions(
        self,
        *,
        grayscale,
        face_box: BoundingBox,
    ) -> dict[str, BoundingBox]:
        if self.eye_cascade is None:
            return {}

        x = face_box.x
        y = face_box.y
        width = face_box.width
        height = face_box.height
        face_roi = grayscale[y : y + height, x : x + width]
        eyes = self.eye_cascade.detectMultiScale(
            face_roi,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(max(width // 8, 12), max(height // 8, 12)),
        )

        labeled_eyes: dict[str, BoundingBox] = {}
        eye_candidates = sorted(
            ((int(ex), int(ey), int(ew), int(eh)) for ex, ey, ew, eh in eyes),
            key=lambda item: item[0],
        )[:2]
        for label, (ex, ey, ew, eh) in zip(("left_eye", "right_eye"), eye_candidates):
            labeled_eyes[label] = BoundingBox(
                x=x + ex,
                y=y + ey,
                width=ew,
                height=eh,
            )
        return labeled_eyes


def build_face_detector(settings: Settings) -> FaceDetector:
    """Build the configured face detector provider."""

    backend = settings.face_detector_backend.strip().lower()
    if backend in {"", "noop", "none", "disabled"}:
        return NoOpFaceDetector()
    if backend in {"opencv", "opencv_haar", "haar"}:
        return OpenCVHaarFaceDetector()
    raise RuntimeError(
        f"Unsupported face detector backend `{settings.face_detector_backend}`.",
    )
