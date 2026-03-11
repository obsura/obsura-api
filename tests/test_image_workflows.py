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

