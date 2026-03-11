from __future__ import annotations


def test_pattern_from_selection_and_search(client) -> None:
    pattern_response = client.post(
        "/api/v1/studio/patterns/from-selection",
        json={
            "name": "Infrastructure Domain",
            "selected_value": "internal.example.com",
            "description": "Protect the internal infrastructure domain",
            "category": "infra",
            "tags": ["ops", "safe-share"],
            "transformation": {
                "mode": "semantic",
                "semantic_label": "INTERNAL_DOMAIN",
            },
        },
    )
    assert pattern_response.status_code == 201
    pattern = pattern_response.json()

    configuration_response = client.post(
        "/api/v1/studio/configurations",
        json={
            "kind": "pack",
            "name": "Infrastructure Pack",
            "description": "Reusable infrastructure-safe sharing pack",
            "category": "infra",
            "tags": ["ops"],
            "pattern_ids": [pattern["id"]],
            "custom_entity_ids": [],
            "metadata": {"team": "platform"},
        },
    )
    assert configuration_response.status_code == 201
    configuration = configuration_response.json()
    assert configuration["metadata"]["team"] == "platform"

    search_response = client.get("/api/v1/studio/search", params={"q": "infra"})
    assert search_response.status_code == 200
    kinds = {item["kind"] for item in search_response.json()}
    assert "pattern" in kinds
    assert "configuration" in kinds

