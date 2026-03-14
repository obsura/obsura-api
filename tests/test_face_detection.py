from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from obsura_api.core.settings import Settings
from obsura_api.domain.common import BoundingBox
from obsura_api.services.providers import faces as faces_module
from obsura_api.services.providers.faces import DetectedFaceRegion, build_face_detector


def test_build_face_detector_uses_configured_backend(monkeypatch) -> None:
    class StubFaceDetector:
        name = "opencv-haar-face-detector"
        supported = True

        def detect_faces(self, image_bytes: bytes) -> list[DetectedFaceRegion]:
            return []

    monkeypatch.setattr(faces_module, "OpenCVHaarFaceDetector", StubFaceDetector)
    settings = Settings(face_detector_backend="opencv_haar", _env_file=None)

    detector = build_face_detector(settings)

    assert detector.name == "opencv-haar-face-detector"
    assert detector.supported is True


def test_build_face_detector_rejects_unknown_backend() -> None:
    settings = Settings(face_detector_backend="mystery-backend", _env_file=None)

    with pytest.raises(RuntimeError, match="Unsupported face detector backend"):
        build_face_detector(settings)


def test_image_analysis_detects_faces_from_provider(client) -> None:
    class FakeFaceDetector:
        name = "fake-face-detector"
        supported = True

        def detect_faces(self, image_bytes: bytes) -> list[DetectedFaceRegion]:
            return [
                DetectedFaceRegion(
                    region=BoundingBox(x=2, y=2, width=10, height=10),
                    subregions={
                        "left_eye": BoundingBox(x=4, y=4, width=2, height=2),
                        "right_eye": BoundingBox(x=8, y=4, width=2, height=2),
                    },
                    confidence=0.97,
                )
            ]

    client.app.state.container.face_detector = FakeFaceDetector()
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("faces.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "Auto face review",
                    "content_type": "image",
                    "detect_faces": True,
                    "persist_job": False,
                }
            )
        },
    )

    assert response.status_code == 200
    findings = response.json()["data"]["findings"]
    assert [item["kind"] for item in findings] == [
        "face_region",
        "face_subregion",
        "face_subregion",
    ]


def test_image_transform_uses_detected_faces_with_configuration_default(client) -> None:
    class FakeFaceDetector:
        name = "fake-face-detector"
        supported = True

        def detect_faces(self, image_bytes: bytes) -> list[DetectedFaceRegion]:
            return [
                DetectedFaceRegion(
                    region=BoundingBox(x=2, y=2, width=8, height=8),
                    subregions={},
                    confidence=0.95,
                )
            ]

    client.app.state.container.face_detector = FakeFaceDetector()
    configuration_response = client.post(
        "/api/v1/studio/configurations",
        json={
            "kind": "profile",
            "name": "Face Mask Profile",
            "default_image_transformation": {
                "mode": "mask",
                "overlay_color": "#000000",
            },
        },
    )
    assert configuration_response.status_code == 201
    configuration_id = configuration_response.json()["data"]["id"]

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("faces-transform.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "Auto face transform",
                    "content_type": "image",
                    "configuration_ids": [configuration_id],
                    "detect_faces": True,
                    "persist_job": False,
                }
            )
        },
    )

    assert response.status_code == 200
    transformed = Image.open(
        BytesIO(
            client.app.state.container.storage.read_stored_bytes(
                response.json()["data"]["stored_output_path"]
            )
        )
    )
    assert transformed.getpixel((4, 4)) != (255, 255, 255)
