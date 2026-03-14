from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

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
        supported_languages = ("en", "es")
        custom_recognizers_configured = True

        def __init__(
            self,
            *,
            language: str,
            model_name: str,
            score_threshold: float,
            supported_languages: tuple[str, ...],
            model_map: dict[str, str],
            recognizers_path,
        ) -> None:
            self.language = language
            self.model_name = model_name
            self.score_threshold = score_threshold
            self.supported_languages = supported_languages
            self.model_map = model_map
            self.recognizers_path = recognizers_path

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
            return []

    monkeypatch.setattr(pii_module, "PresidioPIIDetector", StubPIIDetector)
    settings = Settings(
        pii_backend="presidio",
        pii_language="en",
        presidio_model="en_core_web_sm",
        presidio_score_threshold=0.42,
        presidio_supported_languages=("en", "es"),
        presidio_model_map={"en": "en_core_web_sm", "es": "es_core_news_sm"},
        presidio_recognizers_path="config/presidio.yml",
        _env_file=None,
    )

    detector = build_pii_detector(settings)

    assert detector.name == "presidio-pii-detector"
    assert detector.supported is True
    assert detector.language == "en"
    assert detector.model_name == "en_core_web_sm"
    assert detector.score_threshold == 0.42
    assert detector.supported_languages == ("en", "es")
    assert detector.model_map["es"] == "es_core_news_sm"
    assert Path(detector.recognizers_path).parts[-2:] == ("config", "presidio.yml")


def test_build_pii_detector_rejects_unknown_backend() -> None:
    settings = Settings(pii_backend="mystery-backend", _env_file=None)

    with pytest.raises(RuntimeError, match="Unsupported PII detector backend"):
        build_pii_detector(settings)


def test_text_analysis_detects_presidio_entities_from_provider(client) -> None:
    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True
        supported_languages = ("en",)
        custom_recognizers_configured = False

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
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
        supported_languages = ("en",)
        custom_recognizers_configured = False

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
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
        supported_languages = ("en",)
        custom_recognizers_configured = False

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
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


def test_text_analysis_passes_pii_detection_options_to_provider(client) -> None:
    captured: dict[str, object] = {}

    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True
        supported_languages = ("en", "es")
        custom_recognizers_configured = True

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
            captured["text"] = text
            captured["language"] = language
            captured["entity_allow_list"] = entity_allow_list
            captured["context_words"] = context_words
            return []

    client.app.state.container.pii_detector = FakePIIDetector()

    response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": "Correo de contacto: juan@example.com",
            "persist_job": False,
            "pii_detection": {
                "language": "es",
                "entity_allow_list": ["email_address"],
                "context_words": ["correo", "contacto"],
            },
        },
    )

    assert response.status_code == 200
    assert captured == {
        "text": "Correo de contacto: juan@example.com",
        "language": "es",
        "entity_allow_list": ["EMAIL_ADDRESS"],
        "context_words": ["correo", "contacto"],
    }


def test_text_analysis_uses_configuration_pii_detection_defaults(client) -> None:
    configuration_response = client.post(
        "/api/v1/studio/configurations",
        json={
            "kind": "pack",
            "name": "Arabic Presidio Pack",
            "pii_detection": {
                "language": "ar",
                "entity_allow_list": ["PERSON", "PHONE_NUMBER"],
                "context_words": ["المريض", "الهاتف"],
            },
        },
    )
    assert configuration_response.status_code == 201
    configuration_id = configuration_response.json()["data"]["id"]

    captured: dict[str, object] = {}

    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True
        supported_languages = ("en", "ar")
        custom_recognizers_configured = False

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
            captured["language"] = language
            captured["entity_allow_list"] = entity_allow_list
            captured["context_words"] = context_words
            return []

    client.app.state.container.pii_detector = FakePIIDetector()

    response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": "رقم الهاتف 01000000000",
            "persist_job": False,
            "configuration_ids": [configuration_id],
        },
    )

    assert response.status_code == 200
    assert captured == {
        "language": "ar",
        "entity_allow_list": ["PERSON", "PHONE_NUMBER"],
        "context_words": ["المريض", "الهاتف"],
    }


def test_bulk_text_analysis_passes_pii_detection_options_to_provider(client) -> None:
    captured: list[dict[str, object]] = []

    class FakePIIDetector:
        name = "fake-pii-detector"
        supported = True
        supported_languages = ("en",)
        custom_recognizers_configured = False

        def detect_entities(
            self,
            text: str,
            *,
            language: str | None = None,
            entity_allow_list: list[str] | None = None,
            context_words: list[str] | None = None,
        ) -> list[DetectedPIIEntity]:
            captured.append(
                {
                    "text": text,
                    "language": language,
                    "entity_allow_list": entity_allow_list,
                    "context_words": context_words,
                },
            )
            return []

    client.app.state.container.pii_detector = FakePIIDetector()

    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "pii_detection": {
                "language": "en",
                "entity_allow_list": ["person"],
                "context_words": ["customer"],
            },
            "items": [
                {"content": "John Doe"},
                {"content": "Jane Doe"},
            ],
        },
    )

    assert response.status_code == 201
    assert captured == [
        {
            "text": "John Doe",
            "language": "en",
            "entity_allow_list": ["PERSON"],
            "context_words": ["customer"],
        },
        {
            "text": "Jane Doe",
            "language": "en",
            "entity_allow_list": ["PERSON"],
            "context_words": ["customer"],
        },
    ]
