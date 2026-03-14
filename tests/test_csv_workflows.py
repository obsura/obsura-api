from __future__ import annotations

import json


def test_csv_analyze_returns_cell_aware_findings(client) -> None:
    response = client.post(
        "/api/v1/workflows/csv/analyze",
        files={"file": ("contacts.csv", b"email,name\njohn@example.com,John Doe\n", "text/csv")},
        data={"manifest_json": json.dumps({"persist_job": False})},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    email_finding = next(item for item in body["findings"] if item["entity_type"] == "EMAIL_ADDRESS")
    assert email_finding["kind"] == "structured_field"
    assert email_finding["metadata"]["csv_row_number"] == 2
    assert email_finding["metadata"]["csv_column_index"] == 1
    assert email_finding["metadata"]["csv_column_name"] == "email"
    assert body["headers"] == ["email", "name"]
    assert body["row_count"] == 1


def test_csv_transform_masks_cells_and_escapes_formula_export(client) -> None:
    response = client.post(
        "/api/v1/workflows/csv/transform",
        files={
            "file": (
                "records.csv",
                b"email,token,formula\njohn@example.com,secret,=1+1\n",
                "text/csv",
            )
        },
        data={"manifest_json": json.dumps({"persist_job": False, "exact_values": ["secret"]})},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_rows"][0][0] == "[EMAIL]"
    assert body["output_rows"][0][1] == "[REDACTED]"
    assert body["output_rows"][0][2] == "=1+1"
    assert "'=1+1" in body["output_csv"]
    assert body["formula_escape_count"] == 1
    assert body["summary"]["replacement_count"] == 2
    assert body["summary"]["formula_escape_count"] == 1


def test_csv_review_and_transform_job_flow(client) -> None:
    csv_bytes = b"email,token\njohn@example.com,secret\n"

    analyze_response = client.post(
        "/api/v1/workflows/csv/analyze",
        files={"file": ("review.csv", csv_bytes, "text/csv")},
        data={"manifest_json": json.dumps({"exact_values": ["secret"]})},
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()["data"]
    job_id = analysis["job_id"]
    assert job_id

    review_response = client.post(
        f"/api/v1/jobs/{job_id}/review",
        json={
            "decisions": [
                {
                    "finding_id": finding["id"],
                    "decision": "approved",
                }
                for finding in analysis["findings"]
            ]
        },
    )
    assert review_response.status_code == 200

    transform_response = client.post(
        "/api/v1/workflows/csv/transform-job",
        files={"file": ("review.csv", csv_bytes, "text/csv")},
        data={"manifest_json": json.dumps({"job_id": job_id})},
    )
    assert transform_response.status_code == 200
    transformed = transform_response.json()["data"]
    assert "[EMAIL]" in transformed["output_csv"]
    assert "[REDACTED]" in transformed["output_csv"]

    job_response = client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["content_type"] == "csv"
    assert job["source_text"] is None
    assert job["outputs"][0]["output_text"] is None
    assert job["outputs"][0]["metadata"]["formula_escape_count"] == 0


def test_csv_transform_job_rejects_changed_cell_value(client) -> None:
    original_csv = b"email\njohn@example.com\n"
    changed_csv = b"email\njane@example.com\n"

    analyze_response = client.post(
        "/api/v1/workflows/csv/analyze",
        files={"file": ("review.csv", original_csv, "text/csv")},
        data={"manifest_json": json.dumps({})},
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()["data"]

    transform_response = client.post(
        "/api/v1/workflows/csv/transform-job",
        files={"file": ("review.csv", changed_csv, "text/csv")},
        data={"manifest_json": json.dumps({"job_id": analysis["job_id"], "include_pending": True})},
    )

    assert transform_response.status_code == 422
    body = transform_response.json()
    assert body["success"] is False
    assert "does not match the reviewed job" in body["error"]["message"]


def test_csv_analyze_rejects_non_utf8_upload(client) -> None:
    response = client.post(
        "/api/v1/workflows/csv/analyze",
        files={"file": ("latin1.csv", b"name\ncaf\xe9\n", "text/csv")},
        data={"manifest_json": json.dumps({"persist_job": False})},
    )

    assert response.status_code == 415
    body = response.json()
    assert body["success"] is False
    assert "UTF-8" in body["error"]["message"]
