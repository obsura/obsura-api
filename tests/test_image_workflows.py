from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from obsura_api.app import create_app
from obsura_api.core.settings import Settings
from obsura_api.domain.common import BoundingBox
from obsura_api.services.providers.ocr import OCRBlock, OCRToken


class FakeOCRProvider:
    name = "fake-ocr"
    supported = True

    def __init__(self, blocks: list[OCRBlock]) -> None:
        self.blocks = blocks

    def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
        return self.blocks


def _resolve_stored_path(client, storage_reference: str) -> Path:
    return client.app.state.container.storage.resolve_stored_path(storage_reference)


def _open_stored_image(client, storage_reference: str) -> Image.Image:
    image_bytes = client.app.state.container.storage.read_stored_bytes(storage_reference)
    return Image.open(BytesIO(image_bytes))


def test_image_region_transformation_persists_output(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("example.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "Masked screenshot region",
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 0, "y": 0, "width": 10, "height": 10},
                            "transformation": {
                                "mode": "mask",
                                "overlay_color": "#000000",
                            },
                        }
                    ],
                }
            )
        },
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["stored_output_path"].startswith("outputs/")
    assert body["stored_input_path"] is None
    media_response = client.get(body["media_url"])
    assert media_response.status_code == 200
    transformed = Image.open(BytesIO(media_response.content))
    assert transformed.getpixel((5, 5)) != (255, 255, 255)
    assert not list(client.app.state.container.settings.storage_root.rglob("*.png"))


def test_image_region_defaults_to_blur_without_explicit_transformation(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    for x in range(10):
        for y in range(20):
            image.putpixel((x, y), (0, 0, 0))

    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("default-blur.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 6, "y": 0, "width": 8, "height": 20},
                        }
                    ]
                }
            )
        },
    )

    assert response.status_code == 200
    transformed = _open_stored_image(client, response.json()["data"]["stored_output_path"])
    boundary_pixel = transformed.getpixel((9, 10))
    assert boundary_pixel != (0, 0, 0)
    assert boundary_pixel != (255, 255, 255)


def test_reviewed_image_job_transform_uses_persisted_findings(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    analysis_response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("review.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "Image review job",
                    "content_type": "image",
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 0, "y": 0, "width": 10, "height": 10},
                        }
                    ],
                    "persist_job": True,
                }
            )
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]
    finding_id = analysis["findings"][0]["id"]

    transform_without_review = client.post(
        "/api/v1/workflows/images/transform-job",
        json={"job_id": analysis["job_id"]},
    )
    assert transform_without_review.status_code == 200
    unchanged = _open_stored_image(
        client,
        transform_without_review.json()["data"]["stored_output_path"],
    )
    assert unchanged.getpixel((5, 5)) == (255, 255, 255)

    review_response = client.post(
        f"/api/v1/jobs/{analysis['job_id']}/review",
        json={
            "decisions": [
                {
                    "finding_id": finding_id,
                    "decision": "approved",
                    "transformation": {
                        "mode": "mask",
                        "overlay_color": "#000000",
                    },
                }
            ]
        },
    )
    assert review_response.status_code == 200

    transform_with_review = client.post(
        "/api/v1/workflows/images/transform-job",
        json={"job_id": analysis["job_id"]},
    )
    assert transform_with_review.status_code == 200
    transformed = _open_stored_image(
        client,
        transform_with_review.json()["data"]["stored_output_path"],
    )
    assert transformed.getpixel((5, 5)) != (255, 255, 255)


def test_image_transform_supports_padding_border_and_label_options(client) -> None:
    image = Image.new("RGB", (30, 30), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("styled.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 10, "y": 10, "width": 8, "height": 8},
                            "transformation": {
                                "mode": "overlay",
                                "overlay_color": "#000000",
                                "overlay_label": "HIDDEN",
                                "overlay_shape": "rectangle",
                                "region_padding": 4,
                                "outline_color": "#ff0000",
                                "outline_width": 2,
                                "label_background_color": "#000000",
                                "label_color": "#ffffff",
                                "label_position": "outside_bottom",
                                "label_font_family": "mono",
                                "label_font_size": 18,
                            },
                        }
                    ]
                }
            )
        },
    )

    assert response.status_code == 200
    transformed = _open_stored_image(client, response.json()["data"]["stored_output_path"])
    left_border_pixels = {transformed.getpixel((x, y)) for x in range(6, 9) for y in range(8, 19)}
    assert (255, 0, 0) in left_border_pixels
    assert transformed.getpixel((12, 12)) == (0, 0, 0)


def test_screenshot_ocr_analysis_uses_saved_patterns(client) -> None:
    client.app.state.container.ocr_provider = FakeOCRProvider(
        [
            OCRBlock(
                text="internal.example.com",
                region=BoundingBox(x=2, y=2, width=12, height=6),
                confidence=0.97,
                tokens=[
                    OCRToken(
                        text="internal.example.com",
                        region=BoundingBox(x=2, y=2, width=12, height=6),
                        confidence=0.97,
                    )
                ],
            )
        ]
    )

    pattern_response = client.post(
        "/api/v1/studio/patterns/from-selection",
        json={
            "name": "Internal Domain",
            "selected_value": "internal.example.com",
            "transformation": {
                "mode": "semantic",
                "semantic_label": "INTERNAL_DOMAIN",
            },
        },
    )
    assert pattern_response.status_code == 201
    pattern_id = pattern_response.json()["data"]["id"]

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("screenshot.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "Screenshot OCR review",
                    "content_type": "screenshot",
                    "detect_text": True,
                    "apply_builtins": False,
                    "pattern_ids": [pattern_id],
                    "persist_job": True,
                }
            )
        },
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["job_id"]
    assert body["findings"][0]["source"] == "ocr"
    assert body["findings"][0]["entity_type"] == "Internal Domain"
    assert body["findings"][0]["region"] == {"x": 2, "y": 2, "width": 12, "height": 6}


def test_ocr_derived_image_finding_can_be_reviewed_and_transformed(client) -> None:
    client.app.state.container.ocr_provider = FakeOCRProvider(
        [
            OCRBlock(
                text="token alpha",
                region=BoundingBox(x=0, y=0, width=12, height=10),
                confidence=0.91,
                tokens=[
                    OCRToken(
                        text="token",
                        region=BoundingBox(x=0, y=0, width=5, height=10),
                        confidence=0.91,
                    ),
                    OCRToken(
                        text="alpha",
                        region=BoundingBox(x=6, y=0, width=6, height=10),
                        confidence=0.91,
                    ),
                ],
            )
        ]
    )

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    analysis_response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("ocr.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "OCR image review job",
                    "content_type": "screenshot",
                    "detect_text": True,
                    "apply_builtins": False,
                    "exact_values": ["alpha"],
                    "persist_job": True,
                    "default_transformation": {
                        "mode": "mask",
                        "overlay_color": "#000000",
                    },
                }
            )
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]
    finding = analysis["findings"][0]
    assert finding["region"] == {"x": 6, "y": 0, "width": 6, "height": 10}

    review_response = client.post(
        f"/api/v1/jobs/{analysis['job_id']}/review",
        json={
            "decisions": [
                {
                    "finding_id": finding["id"],
                    "decision": "approved",
                }
            ]
        },
    )
    assert review_response.status_code == 200

    transform_response = client.post(
        "/api/v1/workflows/images/transform-job",
        json={"job_id": analysis["job_id"]},
    )
    assert transform_response.status_code == 200
    transformed = _open_stored_image(
        client,
        transform_response.json()["data"]["stored_output_path"],
    )
    assert transformed.getpixel((8, 5)) != (255, 255, 255)


def test_safe_share_image_transform_upgrades_implicit_ocr_blur_to_overlay(client) -> None:
    client.app.state.container.ocr_provider = FakeOCRProvider(
        [
            OCRBlock(
                text="token alpha",
                region=BoundingBox(x=0, y=0, width=12, height=10),
                confidence=0.91,
                tokens=[
                    OCRToken(
                        text="token",
                        region=BoundingBox(x=0, y=0, width=5, height=10),
                        confidence=0.91,
                    ),
                    OCRToken(
                        text="alpha",
                        region=BoundingBox(x=6, y=0, width=6, height=10),
                        confidence=0.91,
                    ),
                ],
            )
        ]
    )

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("ocr-safe-share.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "content_type": "screenshot",
                    "detect_text": True,
                    "apply_builtins": False,
                    "exact_values": ["alpha"],
                    "output_intent": "safe_share",
                    "persist_job": False,
                }
            )
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_intent"] == "safe_share"
    assert body["share_policy"]["security_rules_enforced"] is True
    assert body["share_policy"]["auto_adjusted"] is True
    transformed = _open_stored_image(client, body["stored_output_path"])
    assert transformed.getpixel((8, 5)) == (17, 17, 17)


def test_safe_share_image_transform_rejects_explicit_ocr_blur(client) -> None:
    client.app.state.container.ocr_provider = FakeOCRProvider(
        [
            OCRBlock(
                text="token alpha",
                region=BoundingBox(x=0, y=0, width=12, height=10),
                confidence=0.91,
                tokens=[
                    OCRToken(
                        text="token",
                        region=BoundingBox(x=0, y=0, width=5, height=10),
                        confidence=0.91,
                    ),
                    OCRToken(
                        text="alpha",
                        region=BoundingBox(x=6, y=0, width=6, height=10),
                        confidence=0.91,
                    ),
                ],
            )
        ]
    )

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("ocr-safe-share.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "content_type": "screenshot",
                    "detect_text": True,
                    "apply_builtins": False,
                    "exact_values": ["alpha"],
                    "output_intent": "safe_share",
                    "default_transformation": {
                        "mode": "blur",
                        "blur_radius": 12,
                    },
                    "persist_job": False,
                }
            )
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "does not allow blur or pixelation" in body["error"]["message"]


def test_persisted_image_job_hides_source_reference_and_raw_ocr_text(client) -> None:
    client.app.state.container.ocr_provider = FakeOCRProvider(
        [
            OCRBlock(
                text="secret alpha",
                region=BoundingBox(x=0, y=0, width=12, height=10),
                confidence=0.91,
                tokens=[
                    OCRToken(
                        text="secret",
                        region=BoundingBox(x=0, y=0, width=6, height=10),
                        confidence=0.91,
                    ),
                    OCRToken(
                        text="alpha",
                        region=BoundingBox(x=7, y=0, width=5, height=10),
                        confidence=0.91,
                    ),
                ],
            )
        ]
    )

    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    analysis_response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("ocr.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "OCR image review job",
                    "content_type": "screenshot",
                    "detect_text": True,
                    "apply_builtins": False,
                    "exact_values": ["alpha"],
                    "persist_job": True,
                }
            )
        },
    )

    assert analysis_response.status_code == 200
    job_id = analysis_response.json()["data"]["job_id"]

    job_response = client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["source_file_path"] is None
    assert job["findings"][0]["matched_text_preview"] is None
    assert "ocr_text" not in job["findings"][0]["metadata"]
    assert job["findings"][0]["metadata"]["ocr_text_hash"]


def test_image_workflow_rejects_invalid_manifest_json(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("example.png", buffer.getvalue(), "image/png")},
        data={"manifest_json": "{not-json"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"


def test_image_workflow_rejects_unsupported_content_type(client) -> None:
    response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("example.txt", b"not an image", "text/plain")},
        data={"manifest_json": "{}"},
    )

    assert response.status_code == 415
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unsupported_media_type"


def test_image_workflow_rejects_oversized_upload(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'obsura.db'}",
        storage_root=tmp_path / "storage",
        auto_create_schema=True,
        ocr_backend="noop",
        face_detector_backend="noop",
        max_upload_bytes=64,
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        image = Image.new("RGB", (20, 20), color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        response = test_client.post(
            "/api/v1/workflows/images/analyze",
            files={"file": ("large.png", buffer.getvalue(), "image/png")},
            data={"manifest_json": "{}"},
        )

    assert response.status_code == 413
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "content_too_large"


def test_image_workflow_rejects_out_of_bounds_region(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("bounds.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 15, "y": 15, "width": 10, "height": 10},
                        }
                    ]
                }
            )
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["message"].startswith("Image region is outside")


def test_image_analysis_can_disable_source_persistence(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    analysis_response = client.post(
        "/api/v1/workflows/images/analyze",
        files={"file": ("review.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "title": "Image review job",
                    "content_type": "image",
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 0, "y": 0, "width": 10, "height": 10},
                        }
                    ],
                    "persist_job": True,
                    "persist_source_content": False,
                }
            )
        },
    )

    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]
    assert analysis["stored_input_path"] is None

    transform_response = client.post(
        "/api/v1/workflows/images/transform-job",
        json={"job_id": analysis["job_id"]},
    )

    assert transform_response.status_code == 400
    body = transform_response.json()
    assert body["success"] is False
    assert body["error"]["message"].startswith("Job does not retain a source image")


def test_image_workflow_rejects_invalid_overlay_color(client) -> None:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/workflows/images/transform",
        files={"file": ("color.png", buffer.getvalue(), "image/png")},
        data={
            "manifest_json": json.dumps(
                {
                    "regions": [
                        {
                            "kind": "image_region",
                            "source": "manual",
                            "entity_type": "SECRET_REGION",
                            "entity_name": "Secret block",
                            "region": {"x": 0, "y": 0, "width": 10, "height": 10},
                            "transformation": {
                                "mode": "mask",
                                "overlay_color": "red",
                            },
                        }
                    ]
                }
            )
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
