from __future__ import annotations


def test_text_review_and_transform_flow(client) -> None:
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
    pattern = pattern_response.json()["data"]

    analysis_response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "title": "Terminal snippet",
            "content": "Connect to https://internal.example.com from 10.0.0.1",
            "pattern_ids": [pattern["id"]],
            "persist_source_content": True,
        },
    )
    assert analysis_response.status_code == 200
    analysis_body = analysis_response.json()
    assert analysis_body["success"] is True
    analysis = analysis_body["data"]
    assert analysis["job_id"]
    assert len(analysis["findings"]) >= 2

    review_payload = {"decisions": []}
    for finding in analysis["findings"]:
        review_payload["decisions"].append(
            {
                "finding_id": finding["id"],
                "decision": "approved" if finding["entity_type"] == "Internal Domain" else "rejected",
            },
        )

    review_response = client.post(
        f"/api/v1/jobs/{analysis['job_id']}/review",
        json=review_payload,
    )
    assert review_response.status_code == 200

    transform_response = client.post(
        "/api/v1/workflows/text/transform",
        json={"job_id": analysis["job_id"]},
    )
    assert transform_response.status_code == 200
    transformed = transform_response.json()["data"]
    assert transformed["output_text"] == "Connect to https://[INTERNAL_DOMAIN] from 10.0.0.1"

    job_response = client.get(f"/api/v1/jobs/{analysis['job_id']}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["outputs"]


def test_stable_alias_workflow(client) -> None:
    response = client.post(
        "/api/v1/workflows/text/analyze-transform",
        json={
            "content": "customer=acme customer=acme customer=globex",
            "exact_values": ["acme", "globex"],
            "default_transformation": {
                "mode": "stable_alias",
                "alias_prefix": "CUSTOMER",
            },
            "persist_job": False,
        },
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_text"] == "customer=CUSTOMER_1 customer=CUSTOMER_1 customer=CUSTOMER_2"


def test_text_transform_requires_explicit_pending_opt_in(client) -> None:
    analysis_response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": "secret=alpha",
            "exact_values": ["alpha"],
            "persist_source_content": True,
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]

    default_transform_response = client.post(
        "/api/v1/workflows/text/transform",
        json={"job_id": analysis["job_id"]},
    )
    assert default_transform_response.status_code == 200
    assert default_transform_response.json()["data"]["output_text"] == "secret=alpha"

    pending_transform_response = client.post(
        "/api/v1/workflows/text/transform",
        json={"job_id": analysis["job_id"], "include_pending": True},
    )
    assert pending_transform_response.status_code == 200
    assert pending_transform_response.json()["data"]["output_text"] == "secret=[REDACTED]"
