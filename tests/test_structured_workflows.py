from __future__ import annotations


def test_structured_analyze_returns_path_aware_findings(client) -> None:
    response = client.post(
        "/api/v1/workflows/structured/analyze",
        json={
            "data": {
                "patient": {
                    "email": "john@example.com",
                    "notes": "ok",
                }
            },
            "persist_job": False,
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    email_finding = next(
        item for item in body["findings"] if item["entity_type"] == "EMAIL_ADDRESS"
    )
    assert email_finding["kind"] == "structured_field"
    assert email_finding["metadata"]["structured_path"] == "$.patient.email"
    assert email_finding["metadata"]["structured_path_tokens"] == ["s:patient", "s:email"]


def test_structured_transform_masks_nested_values(client) -> None:
    response = client.post(
        "/api/v1/workflows/structured/transform",
        json={
            "data": {
                "patient": {
                    "email": "john@example.com",
                    "name": "John Doe",
                },
                "audit": [
                    {
                        "token": "secret",
                    }
                ],
            },
            "exact_values": ["secret"],
            "persist_job": False,
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_data"]["patient"]["email"] == "[EMAIL]"
    assert body["output_data"]["audit"][0]["token"] == "[REDACTED]"
    assert body["artifacts"][0]["name"] == "output_data"
    assert body["artifacts"][0]["kind"] == "json"
    assert {item["path"] for item in body["replacements"]} == {
        "$.patient.email",
        "$.audit[0].token",
    }


def test_structured_review_and_transform_job_flow(client) -> None:
    analysis_response = client.post(
        "/api/v1/workflows/structured/analyze",
        json={
            "title": "Customer profile",
            "data": {
                "customer": {
                    "email": "john@example.com",
                    "id": "CUST-123",
                }
            },
            "exact_values": ["CUST-123"],
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]
    job_id = analysis["job_id"]
    assert job_id

    review_response = client.post(
        f"/api/v1/jobs/{job_id}/review",
        json={
            "decisions": [
                {
                    "finding_id": finding["id"],
                    "decision": "approved"
                    if finding["entity_type"] == "EXACT_VALUE"
                    else "rejected",
                }
                for finding in analysis["findings"]
            ]
        },
    )
    assert review_response.status_code == 200

    transform_response = client.post(
        "/api/v1/workflows/structured/transform-job",
        json={
            "job_id": job_id,
            "data": {
                "customer": {
                    "email": "john@example.com",
                    "id": "CUST-123",
                }
            },
        },
    )
    assert transform_response.status_code == 200
    transformed = transform_response.json()["data"]
    assert transformed["output_data"]["customer"]["email"] == "john@example.com"
    assert transformed["output_data"]["customer"]["id"] == "[REDACTED]"

    job_response = client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["source_text"] is None
    assert job["outputs"][0]["output_text"] is None
    assert job["outputs"][0]["artifact"]["name"] == "output_data"
    assert job["findings"][0]["metadata"]["structured_path"].startswith("$.customer")


def test_structured_transform_job_rejects_non_string_leaf(client) -> None:
    analysis_response = client.post(
        "/api/v1/workflows/structured/analyze",
        json={
            "data": {
                "profile": {
                    "email": "john@example.com",
                }
            },
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]

    transform_response = client.post(
        "/api/v1/workflows/structured/transform-job",
        json={
            "job_id": analysis["job_id"],
            "include_pending": True,
            "data": {
                "profile": {
                    "email": {"nested": "not-a-string"},
                }
            },
        },
    )

    assert transform_response.status_code == 422
    body = transform_response.json()
    assert body["success"] is False
    assert "must resolve to a string value" in body["error"]["message"]


def test_structured_analyze_rejects_excessive_depth(client) -> None:
    payload: object = "leaf"
    for depth in range(18):
        payload = {f"level_{depth}": payload}

    response = client.post(
        "/api/v1/workflows/structured/analyze",
        json={
            "data": payload,
            "persist_job": False,
        },
    )

    assert response.status_code == 413
    body = response.json()
    assert body["success"] is False
    assert "maximum depth" in body["error"]["message"]
