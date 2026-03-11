from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image


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
    body = response.json()
    output_path = Path(body["stored_output_path"])
    assert output_path.exists()
    transformed = Image.open(output_path)
    assert transformed.getpixel((5, 5)) != (255, 255, 255)


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
    analysis = analysis_response.json()
    finding_id = analysis["findings"][0]["id"]

    transform_without_review = client.post(
        "/api/v1/workflows/images/transform-job",
        json={"job_id": analysis["job_id"]},
    )
    assert transform_without_review.status_code == 200
    unchanged_path = Path(transform_without_review.json()["stored_output_path"])
    assert Image.open(unchanged_path).getpixel((5, 5)) == (255, 255, 255)

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
    reviewed_path = Path(transform_with_review.json()["stored_output_path"])
    assert reviewed_path.exists()
    transformed = Image.open(reviewed_path)
    assert transformed.getpixel((5, 5)) != (255, 255, 255)
