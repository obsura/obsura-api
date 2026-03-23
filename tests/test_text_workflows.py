from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from obsura_api.app import create_app
from obsura_api.core.settings import Settings


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
                "decision": "approved"
                if finding["entity_type"] == "Internal Domain"
                else "rejected",
            },
        )

    review_response = client.post(
        f"/api/v1/jobs/{analysis['job_id']}/review",
        json=review_payload,
    )
    assert review_response.status_code == 200

    transform_response = client.post(
        "/api/v1/workflows/text/transform",
        json={
            "job_id": analysis["job_id"],
            "content": "Connect to https://internal.example.com from 10.0.0.1",
        },
    )
    assert transform_response.status_code == 200
    transformed = transform_response.json()["data"]
    assert transformed["output_text"] == "Connect to https://[INTERNAL_DOMAIN] from 10.0.0.1"

    job_response = client.get(f"/api/v1/jobs/{analysis['job_id']}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["source_text"] is None
    assert job["outputs"]
    assert job["outputs"][0]["output_text"] is None


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
        json={"job_id": analysis["job_id"], "content": "secret=alpha"},
    )
    assert default_transform_response.status_code == 200
    assert default_transform_response.json()["data"]["output_text"] == "secret=alpha"

    pending_transform_response = client.post(
        "/api/v1/workflows/text/transform",
        json={"job_id": analysis["job_id"], "content": "secret=alpha", "include_pending": True},
    )
    assert pending_transform_response.status_code == 200
    assert pending_transform_response.json()["data"]["output_text"] == "secret=[REDACTED]"


def test_built_in_technical_detectors_cover_common_secret_shapes(client) -> None:
    response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": (
                "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturepart\n"
                "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n"
                "GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuv\n"
                "password=supersecretvalue\n"
                "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7 example@host\n"
                "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----\n"
            ),
            "pii_detection": {
                "min_confidence": 0.8,
            },
            "persist_job": False,
        },
    )
    assert response.status_code == 200
    findings = response.json()["data"]["findings"]
    entity_types = {item["entity_type"] for item in findings}

    assert "JWT" in entity_types
    assert "AWS_ACCESS_KEY_ID" in entity_types
    assert "GITHUB_TOKEN" in entity_types
    assert "ENV_SECRET" in entity_types
    assert "SECRET_VALUE" in entity_types
    assert "SSH_PUBLIC_KEY" in entity_types
    assert "PRIVATE_KEY" in entity_types


def test_text_transform_supports_partial_mask_for_frontend_customization(client) -> None:
    response = client.post(
        "/api/v1/workflows/text/analyze-transform",
        json={
            "content": "Contact me at john.doe@example.com",
            "exact_values": ["john.doe@example.com"],
            "default_transformation": {
                "mode": "partial_mask",
                "prefix_visible": 2,
                "suffix_visible": 12,
                "mask_character": "*",
            },
            "persist_job": False,
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_text"] == "Contact me at jo******@example.com"


def test_text_transform_supports_redact_mode(client) -> None:
    response = client.post(
        "/api/v1/workflows/text/analyze-transform",
        json={
            "content": "token=supersecret",
            "exact_values": ["supersecret"],
            "default_transformation": {"mode": "redact"},
            "persist_job": False,
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_text"] == "token="


def test_text_transform_supports_hash_mode_with_configured_salt(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'obsura.db'}",
        storage_root=tmp_path / "storage",
        auto_create_schema=True,
        ocr_backend="noop",
        face_detector_backend="noop",
        pii_backend="noop",
        text_hash_salt="0123456789abcdef",
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows/text/analyze-transform",
            json={
                "content": "token=alpha token=alpha",
                "exact_values": ["alpha"],
                "default_transformation": {"mode": "hash"},
                "persist_job": False,
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]
    expected_hash = hashlib.sha256(b"0123456789abcdef:alpha").hexdigest()
    assert body["output_text"] == f"token={expected_hash} token={expected_hash}"


def test_text_transform_rejects_hash_mode_without_configured_salt(client) -> None:
    response = client.post(
        "/api/v1/workflows/text/analyze-transform",
        json={
            "content": "token=alpha",
            "exact_values": ["alpha"],
            "default_transformation": {"mode": "hash"},
            "persist_job": False,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "OBSURA_TEXT_HASH_SALT" in body["error"]["message"]


def test_text_transform_safe_share_persists_output_intent_metadata(client) -> None:
    analysis_response = client.post(
        "/api/v1/workflows/text/analyze",
        json={
            "content": "token=alpha",
            "exact_values": ["alpha"],
            "persist_source_content": True,
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["data"]

    review_response = client.post(
        f"/api/v1/jobs/{analysis['job_id']}/review",
        json={
            "decisions": [
                {
                    "finding_id": analysis["findings"][0]["id"],
                    "decision": "approved",
                }
            ]
        },
    )
    assert review_response.status_code == 200

    transform_response = client.post(
        "/api/v1/workflows/text/transform",
        json={
            "job_id": analysis["job_id"],
            "content": "token=alpha",
            "output_intent": "safe_share",
        },
    )

    assert transform_response.status_code == 200
    body = transform_response.json()["data"]
    assert body["output_intent"] == "safe_share"
    assert body["share_policy"]["security_rules_enforced"] is True
    assert body["artifacts"][0]["name"] == "output_text"
    assert body["artifacts"][0]["intended_use"] == "safe_share"
    assert body["artifacts"][0]["share_ready"] is True
    assert body["artifacts"][0]["primary"] is True

    job_response = client.get(f"/api/v1/jobs/{analysis['job_id']}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["outputs"][0]["metadata"]["output_intent"] == "safe_share"
    assert job["outputs"][0]["artifact"]["name"] == "output_text"
    assert job["outputs"][0]["artifact"]["share_ready"] is True
