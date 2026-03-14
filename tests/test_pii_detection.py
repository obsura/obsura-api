from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from obsura_api.core.settings import Settings
from obsura_api.domain.common import BoundingBox
from obsura_api.services.providers import pii as pii_module
from obsura_api.services.providers.ocr import OCRBlock, OCRToken
from obsura_api.services.providers.pii import DetectedPIIEntity, build_pii_detector


def test_build_pii_detector_uses_configured_backend(monkeypatch) -> None:
    class StubPIIDetector:
        name = "presidio-pii-detector"
        supported = True

        def __init__(self, *, language: str, model_name: str, score_threshold: float) -> None:
            self.language = language
            self.model_name = model_name
            self.score_threshold = score_threshold

        def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
            return []

    monkeypatch.setattr(pii_module, "PresidioPIIDetector", StubPIIDetector)
    settings = Settings(
        pii_backend="presidio",
        pii_language="en",
        presidio_model="en_core_web_sm",
        presidio_score_threshold=0.42,
        _env_file=None,
    )

    detector = build_pii_detector(settings)

    assert detector.name == "presidio-pii-detector"
    assert detector.supported is True
    assert detector.language == "en"
    assert detector.model_name == "en_core_web_sm"
    assert detector.score_threshold == 0.42


def test_build_pii_detector_rejects_unknown_backend() -> None:
    settings = Settings(pii_backend="mystery-backend", _env_file=None)

    with pytest.raises(RuntimeError, match="Unsupported PII detector backend"):
        build_pii_detector(settings)


def test_text_analysis_detects_presidio_entities_from_provider(client) -> None:
    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True

        def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
            start_index = text.index("John Doe")
            return [
                DetectedPIIEntity(
                    entity_type="PERSON",
                    start_index=start_index,
                    end_index=start_index + len("John Doe"),
                    confidence=0.88,
                )
            ]

    client.app.state.container.pii_detector = FakePIIDetector()

    response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": "Customer is John Doe from Cairo",
            "persist_job": False,
        },
    )

    assert response.status_code == 200
    findings = response.json()["data"]["findings"]
    person_finding = next(item for item in findings if item["entity_type"] == "PERSON")
    assert person_finding["source"] == "built_in"
    assert person_finding["entity_name"] == "Person name"
    assert person_finding["confidence"] == 0.88


def test_text_analysis_skips_overlapping_pii_with_existing_builtin(client) -> None:
    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True

        def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
            start_index = text.index("john@example.com")
            return [
                DetectedPIIEntity(
                    entity_type="URL",
                    start_index=start_index + len("john@"),
                    end_index=start_index + len("john@example.com"),
                    confidence=0.5,
                )
            ]

    client.app.state.container.pii_detector = FakePIIDetector()

    response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": "Reach me at john@example.com",
            "persist_job": False,
        },
    )

    assert response.status_code == 200
    entity_types = {item["entity_type"] for item in response.json()["data"]["findings"]}
    assert "EMAIL_ADDRESS" in entity_types
    assert "URL" not in entity_types


def test_image_ocr_analysis_detects_pii_from_provider(client) -> None:
    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True

        def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
            return [
                DetectedPIIEntity(
                    entity_type="PERSON",
                    start_index=0,
                    end_index=len("John Doe"),
                    confidence=0.91,
                )
            ]

    class FakeOCRProvider:
        name = "fake-ocr"
        supported = True

        def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
            return [
                OCRBlock(
                    text="John Doe",
                    region=BoundingBox(x=1, y=2, width=12, height=6),
                    confidence=0.96,
                    tokens=[
                        OCRToken(
                            text="John",
                            region=BoundingBox(x=1, y=2, width=5, height=6),
                            confidence=0.96,
                        ),
                        OCRToken(
                            text="Doe",
                            region=BoundingBox(x=7, y=2, width=6, height=6),
                            confidence=0.96,
                        ),
                    ],
                )
            ]

    client.app.state.container.pii_detector = FakePIIDetector()
    client.app.state.container.ocr_provider = FakeOCRProvider()

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("pii.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "OCR PII review",
                    "content_type": "screenshot",
                    "detect_text": True,
                    "persist_job": False,
                }
            )
        },
    )

    assert response.status_code == 200
    findings = response.json()["data"]["findings"]
    assert findings[0]["source"] == "ocr"
    assert findings[0]["entity_type"] == "PERSON"
    assert findings[0]["region"] == {"x": 1, "y": 2, "width": 12, "height": 6}
