from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from obsura_api.app import create_app
from obsura_api.core.settings import Settings


def create_bulk_text_job(client, *, items, **overrides):
    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "title": overrides.pop("title", "Bulk run"),
            "apply_builtins": overrides.pop("apply_builtins", False),
            "exact_values": overrides.pop("exact_values", ["secret"]),
            "persist_source_content": overrides.pop("persist_source_content", False),
            "items": items,
            **overrides,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def get_job(client, job_id: str) -> dict:
    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    return response.json()["data"]


def approve_all_findings(client, bulk_id: str, job_ids: list[str]) -> dict:
    jobs_payload = []
    for job_id in job_ids:
        job = get_job(client, job_id)
        jobs_payload.append(
            {
                "job_id": job_id,
                "decisions": [
                    {"finding_id": finding["id"], "decision": "approved"}
                    for finding in job["findings"]
                ],
            }
        )

    response = client.post(f"/api/v1/bulk/jobs/{bulk_id}/review", json={"jobs": jobs_payload})
    assert response.status_code == 200
    return response.json()["data"]


def test_bulk_text_analyze_persists_parent_and_child_jobs(client) -> None:
    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "title": "Terminal snippets",
            "apply_builtins": True,
            "exact_values": ["root"],
            "persist_source_content": True,
            "items": [
                {
                    "client_item_id": "item-1",
                    "title": "Snippet 1",
                    "content": "ssh root@10.0.0.1",
                },
                {
                    "client_item_id": "item-2",
                    "title": "Snippet 2",
                    "content": "open https://internal.example.com as root",
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "completed"
    assert data["item_count"] == 2
    assert data["success_count"] == 2
    assert data["failure_count"] == 0
    assert [item["item_index"] for item in data["items"]] == [0, 1]
    assert [item["client_item_id"] for item in data["items"]] == ["item-1", "item-2"]
    assert all(item["status"] == "succeeded" for item in data["items"])
    assert all(item["job_id"] for item in data["items"])
    assert all(item["job_status"] == "analyzed" for item in data["items"])
    assert all(item["summary"]["total"] >= 1 for item in data["items"])
    assert all("finding_count" not in item["summary"] for item in data["items"])

    detail_response = client.get(f"/api/v1/bulk/jobs/{data['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["id"] == data["id"]
    assert [item["client_item_id"] for item in detail["items"]] == ["item-1", "item-2"]

    jobs_response = client.get("/api/v1/jobs", params={"page": 1, "page_size": 10})
    assert jobs_response.status_code == 200
    jobs_body = jobs_response.json()
    assert jobs_body["pagination"]["total_items"] == 2


def test_bulk_text_analyze_supports_partial_failures(client) -> None:
    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "title": "Mixed submission",
            "exact_values": ["secret"],
            "items": [
                {
                    "client_item_id": "valid-item",
                    "title": "Valid",
                    "content": "token=secret",
                },
                {
                    "client_item_id": "blank-item",
                    "title": "Blank",
                    "content": "   ",
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    data = body["data"]
    assert data["status"] == "partial_failure"
    assert data["success_count"] == 1
    assert data["failure_count"] == 1
    assert [item["item_index"] for item in data["items"]] == [0, 1]

    successful_item = data["items"][0]
    failed_item = data["items"][1]
    assert successful_item["status"] == "succeeded"
    assert successful_item["job_id"]
    assert failed_item["status"] == "failed"
    assert failed_item["job_id"] is None
    assert failed_item["error"] == "Item content must not be blank"

    jobs_response = client.get("/api/v1/jobs", params={"page": 1, "page_size": 10})
    assert jobs_response.status_code == 200
    assert jobs_response.json()["pagination"]["total_items"] == 1


def test_bulk_text_analyze_persists_failed_parent_when_all_items_fail(client) -> None:
    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "title": "Invalid batch",
            "items": [
                {"client_item_id": "empty-1", "content": ""},
                {"client_item_id": "empty-2", "content": "   "},
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "failed"
    assert data["item_count"] == 2
    assert data["success_count"] == 0
    assert data["failure_count"] == 2
    assert all(item["status"] == "failed" for item in data["items"])
    assert all(item["job_id"] is None for item in data["items"])

    list_response = client.get("/api/v1/bulk/jobs", params={"page": 1, "page_size": 10})
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["success"] is True
    assert list_body["pagination"]["total_items"] == 1
    assert list_body["data"][0]["status"] == "failed"

    jobs_response = client.get("/api/v1/jobs", params={"page": 1, "page_size": 10})
    assert jobs_response.status_code == 200
    assert jobs_response.json()["pagination"]["total_items"] == 0


def test_bulk_jobs_are_listed_with_pagination(client) -> None:
    for index in range(2):
        response = client.post(
            "/api/v1/bulk/text/analyze",
            json={
                "title": f"Bulk {index}",
                "items": [{"client_item_id": f"item-{index}", "content": f"secret=value-{index}"}],
            },
        )
        assert response.status_code == 201

    page_one = client.get("/api/v1/bulk/jobs", params={"page": 1, "page_size": 1})
    assert page_one.status_code == 200
    page_one_body = page_one.json()
    assert page_one_body["success"] is True
    assert len(page_one_body["data"]) == 1
    assert page_one_body["pagination"]["page"] == 1
    assert page_one_body["pagination"]["page_size"] == 1
    assert page_one_body["pagination"]["total_items"] == 2
    assert page_one_body["pagination"]["has_next"] is True


def test_bulk_text_analyze_rejects_limit_violations(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'bulk-limits.db'}",
        storage_root=tmp_path / "storage",
        auto_create_schema=True,
        max_bulk_text_items=1,
        max_bulk_text_total_characters=5,
        ocr_backend="noop",
        face_detector_backend="noop",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as custom_client:
        too_many_items = custom_client.post(
            "/api/v1/bulk/text/analyze",
            json={
                "items": [
                    {"client_item_id": "one", "content": "abc"},
                    {"client_item_id": "two", "content": "def"},
                ]
            },
        )
        assert too_many_items.status_code == 422
        too_many_body = too_many_items.json()
        assert too_many_body["success"] is False
        assert "configured maximum of 1 items" in too_many_body["error"]["message"]

        too_large = custom_client.post(
            "/api/v1/bulk/text/analyze",
            json={"items": [{"client_item_id": "one", "content": "abcdef"}]},
        )
        assert too_large.status_code == 422
        too_large_body = too_large.json()
        assert too_large_body["success"] is False
        assert "combined content size of 5 characters" in too_large_body["error"]["message"]


def test_bulk_text_analyze_rejects_duplicate_client_item_ids(client) -> None:
    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "items": [
                {"client_item_id": "duplicate", "content": "first"},
                {"client_item_id": "duplicate", "content": "second"},
            ]
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"


def test_bulk_text_analyze_rejects_missing_shared_references(client) -> None:
    response = client.post(
        "/api/v1/bulk/text/analyze",
        json={
            "pattern_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
            "items": [{"client_item_id": "one", "content": "root@10.0.0.1"}],
        },
    )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["message"].startswith("Pattern reference not found")

    list_response = client.get("/api/v1/bulk/jobs", params={"page": 1, "page_size": 10})
    assert list_response.status_code == 200
    assert list_response.json()["pagination"]["total_items"] == 0


def test_bulk_review_updates_child_jobs_and_bulk_progress(client) -> None:
    bulk = create_bulk_text_job(
        client,
        items=[
            {"client_item_id": "item-1", "content": "token=secret"},
            {"client_item_id": "item-2", "content": "secret=alpha"},
        ],
    )
    job_ids = [item["job_id"] for item in bulk["items"]]

    review = approve_all_findings(client, bulk["id"], job_ids)

    assert review["action"] == "review"
    assert review["status"] == "reviewed"
    assert review["success_count"] == 2
    assert review["failure_count"] == 0
    assert review["skipped_count"] == 0
    assert review["reviewed_item_count"] == 2
    assert [item["item_index"] for item in review["items"]] == [0, 1]
    assert all(item["operation_status"] == "succeeded" for item in review["items"])
    assert all(item["bulk_item_status"] == "reviewed" for item in review["items"])
    assert all(item["job_status"] == "reviewed" for item in review["items"])

    detail_response = client.get(f"/api/v1/bulk/jobs/{bulk['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["status"] == "reviewed"
    assert detail["reviewed_item_count"] == 2
    assert detail["transformed_item_count"] == 0
    assert all(item["status"] == "reviewed" for item in detail["items"])

    list_response = client.get("/api/v1/bulk/jobs", params={"page": 1, "page_size": 10})
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["data"][0]["status"] == "reviewed"


def test_bulk_review_supports_mixed_success_and_invalid_finding_refs(client) -> None:
    bulk = create_bulk_text_job(
        client,
        items=[
            {"client_item_id": "item-1", "content": "token=secret"},
            {"client_item_id": "item-2", "content": "secret=alpha"},
        ],
    )
    first_job = get_job(client, bulk["items"][0]["job_id"])

    response = client.post(
        f"/api/v1/bulk/jobs/{bulk['id']}/review",
        json={
            "jobs": [
                {
                    "job_id": bulk["items"][0]["job_id"],
                    "decisions": [
                        {"finding_id": first_job["findings"][0]["id"], "decision": "approved"}
                    ],
                },
                {
                    "job_id": bulk["items"][1]["job_id"],
                    "decisions": [
                        {
                            "finding_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                            "decision": "approved",
                        }
                    ],
                },
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "partially_reviewed"
    assert data["success_count"] == 1
    assert data["failure_count"] == 1
    assert data["skipped_count"] == 0
    assert data["items"][0]["operation_status"] == "succeeded"
    assert data["items"][1]["operation_status"] == "failed"
    assert data["items"][1]["error"].startswith("Finding ")
    assert data["items"][1]["bulk_item_status"] == "succeeded"


def test_bulk_review_rejects_jobs_outside_the_bulk_run(client) -> None:
    bulk = create_bulk_text_job(
        client,
        items=[{"client_item_id": "item-1", "content": "token=secret"}],
    )

    single_job_response = client.post(
        "/api/v1/workflows/text/analyze",
        json={"content": "secret=value", "exact_values": ["value"]},
    )
    assert single_job_response.status_code == 200
    outside_job_id = single_job_response.json()["data"]["job_id"]

    response = client.post(
        f"/api/v1/bulk/jobs/{bulk['id']}/review",
        json={
            "jobs": [
                {
                    "job_id": outside_job_id,
                    "decisions": [
                        {
                            "finding_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                            "decision": "approved",
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["message"].startswith(
        "Bulk review entries must reference jobs in this bulk run"
    )


def test_bulk_transform_generates_outputs_for_reviewed_jobs(client) -> None:
    bulk = create_bulk_text_job(
        client,
        items=[
            {"client_item_id": "item-1", "content": "token=secret"},
            {"client_item_id": "item-2", "content": "api=secret"},
        ],
    )
    job_ids = [item["job_id"] for item in bulk["items"]]
    approve_all_findings(client, bulk["id"], job_ids)

    response = client.post(
        "/api/v1/bulk/text/transform",
        json={
            "bulk_id": bulk["id"],
            "job_overrides": [
                {
                    "job_id": job_ids[0],
                    "content": "token=secret",
                },
                {
                    "job_id": job_ids[1],
                    "content": "api=secret",
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["action"] == "transform"
    assert data["status"] == "transformed"
    assert data["success_count"] == 2
    assert data["failure_count"] == 0
    assert data["skipped_count"] == 0
    assert data["transformed_item_count"] == 2
    assert data["output_count"] == 2
    assert [item["item_index"] for item in data["items"]] == [0, 1]
    assert all(item["operation_status"] == "succeeded" for item in data["items"])
    assert all(item["bulk_item_status"] == "transformed" for item in data["items"])
    assert all(item["output_available"] is True for item in data["items"])
    assert all(item["replacement_count"] >= 1 for item in data["items"])
    assert data["items"][0]["output_text"] == "token=[REDACTED]"
    assert data["items"][1]["output_text"] == "api=[REDACTED]"

    detail_response = client.get(f"/api/v1/bulk/jobs/{bulk['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["status"] == "transformed"
    assert detail["reviewed_item_count"] == 2
    assert detail["transformed_item_count"] == 2
    assert detail["output_count"] == 2
    assert all(item["status"] == "transformed" for item in detail["items"])

    list_response = client.get("/api/v1/bulk/jobs", params={"page": 1, "page_size": 10})
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["data"][0]["status"] == "transformed"


def test_bulk_transform_supports_partial_failures_for_incomplete_items(client) -> None:
    bulk = create_bulk_text_job(
        client,
        persist_source_content=False,
        items=[
            {"client_item_id": "item-1", "content": "token=secret"},
            {"client_item_id": "item-2", "content": "api=secret"},
            {"client_item_id": "item-3", "content": "   "},
        ],
    )
    valid_job_ids = [item["job_id"] for item in bulk["items"] if item["job_id"]]
    approve_all_findings(client, bulk["id"], valid_job_ids)

    response = client.post(
        "/api/v1/bulk/text/transform",
        json={
            "bulk_id": bulk["id"],
            "job_overrides": [
                {
                    "job_id": valid_job_ids[0],
                    "content": "token=secret",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "partially_transformed"
    assert data["success_count"] == 1
    assert data["failure_count"] == 2
    assert [item["item_index"] for item in data["items"]] == [0, 1, 2]
    assert data["items"][0]["operation_status"] == "succeeded"
    assert data["items"][0]["bulk_item_status"] == "transformed"
    assert data["items"][1]["operation_status"] == "failed"
    assert (
        data["items"][1]["error"]
        == "Job does not retain source text; resubmit content to transform it"
    )
    assert data["items"][1]["bulk_item_status"] == "reviewed"
    assert data["items"][2]["operation_status"] == "failed"
    assert data["items"][2]["error"] == "No child job exists for this bulk item"


def test_bulk_transform_rejects_overrides_for_jobs_outside_the_bulk_run(client) -> None:
    bulk = create_bulk_text_job(
        client,
        items=[{"client_item_id": "item-1", "content": "token=secret"}],
    )

    single_job_response = client.post(
        "/api/v1/workflows/text/analyze",
        json={"content": "secret=value", "exact_values": ["value"]},
    )
    assert single_job_response.status_code == 200
    outside_job_id = single_job_response.json()["data"]["job_id"]

    response = client.post(
        "/api/v1/bulk/text/transform",
        json={
            "bulk_id": bulk["id"],
            "job_overrides": [{"job_id": outside_job_id, "content": "secret=value"}],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["message"].startswith(
        "Bulk transform overrides must reference jobs in this bulk run"
    )


def test_bulk_endpoints_return_unified_not_found_errors(client) -> None:
    missing_bulk_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    detail_response = client.get(f"/api/v1/bulk/jobs/{missing_bulk_id}")
    assert detail_response.status_code == 404
    detail_body = detail_response.json()
    assert detail_body["success"] is False
    assert detail_body["error"]["code"] == "not_found"

    review_response = client.post(
        f"/api/v1/bulk/jobs/{missing_bulk_id}/review",
        json={
            "jobs": [
                {
                    "job_id": missing_bulk_id,
                    "decisions": [{"finding_id": missing_bulk_id, "decision": "approved"}],
                }
            ]
        },
    )
    assert review_response.status_code == 404
    review_body = review_response.json()
    assert review_body["success"] is False
    assert review_body["error"]["code"] == "not_found"

    transform_response = client.post(
        "/api/v1/bulk/text/transform",
        json={"bulk_id": missing_bulk_id},
    )
    assert transform_response.status_code == 404
    transform_body = transform_response.json()
    assert transform_body["success"] is False
    assert transform_body["error"]["code"] == "not_found"
