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
    pattern_body = pattern_response.json()
    assert pattern_body["success"] is True
    pattern = pattern_body["data"]

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
    configuration_body = configuration_response.json()
    assert configuration_body["success"] is True
    configuration = configuration_body["data"]
    assert configuration["metadata"]["team"] == "platform"

    search_response = client.get(
        "/api/v1/studio/search",
        params={"q": "infra", "page": 1, "page_size": 10},
    )
    assert search_response.status_code == 200
    search_body = search_response.json()
    assert search_body["success"] is True
    assert search_body["pagination"]["page"] == 1
    kinds = {item["kind"] for item in search_body["data"]}
    assert "pattern" in kinds
    assert "configuration" in kinds


def test_list_patterns_is_paginated_and_validation_errors_are_unified(client) -> None:
    for name in ("Pattern A", "Pattern B"):
        response = client.post(
            "/api/v1/studio/patterns/from-selection",
            json={"name": name, "selected_value": f"{name.lower().replace(' ', '-')}.example.com"},
        )
        assert response.status_code == 201

    page_one = client.get("/api/v1/studio/patterns", params={"page": 1, "page_size": 1})
    assert page_one.status_code == 200
    page_one_body = page_one.json()
    assert page_one_body["success"] is True
    assert len(page_one_body["data"]) == 1
    assert page_one_body["pagination"]["page"] == 1
    assert page_one_body["pagination"]["page_size"] == 1
    assert page_one_body["pagination"]["total_items"] == 2
    assert page_one_body["pagination"]["has_next"] is True

    invalid_search = client.get("/api/v1/studio/search")
    assert invalid_search.status_code == 422
    invalid_body = invalid_search.json()
    assert invalid_body["success"] is False
    assert invalid_body["error"]["code"] == "validation_error"


def test_not_found_errors_use_unified_envelope(client) -> None:
    response = client.get("/api/v1/patterns")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Not Found"
