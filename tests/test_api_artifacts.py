from __future__ import annotations

from obsura_api.app import create_app
from obsura_api.core.settings import Settings
from obsura_api.tools.api_artifacts import build_postman_collection


def test_postman_collection_uses_chained_variables() -> None:
    app = create_app(
        Settings(
            document_extractor_backend="noop",
            ocr_backend="noop",
            face_detector_backend="noop",
            auto_create_schema=True,
            _env_file=None,
        )
    )
    collection = build_postman_collection(app.openapi())

    variables = {item["key"] for item in collection["variable"]}
    assert {"baseUrl", "patternId", "configurationId", "bulkId", "jobId", "findingId"} <= variables

    bulk_folder = next(item for item in collection["item"] if item["name"] == "Bulk Jobs")
    bulk_analyze_request = next(
        item for item in bulk_folder["item"] if item["name"] == "Analyze Bulk Text"
    )
    assert "{{patternId}}" in bulk_analyze_request["request"]["body"]["raw"]
    assert "{{bulkId}}" not in bulk_analyze_request["request"]["body"]["raw"]
    assert bulk_analyze_request["event"]

    bulk_review_request = next(
        item for item in bulk_folder["item"] if item["name"] == "Review Bulk Job"
    )
    assert "{{bulkId}}" in bulk_review_request["request"]["url"]["raw"]
    assert "{{jobId}}" in bulk_review_request["request"]["body"]["raw"]
    assert "{{findingId}}" in bulk_review_request["request"]["body"]["raw"]

    bulk_transform_request = next(
        item for item in bulk_folder["item"] if item["name"] == "Transform Bulk Text"
    )
    assert "{{bulkId}}" in bulk_transform_request["request"]["body"]["raw"]
    assert "{{jobId}}" in bulk_transform_request["request"]["body"]["raw"]

    jobs_folder = next(item for item in collection["item"] if item["name"] == "Jobs")
    get_job_request = next(
        item for item in jobs_folder["item"] if item["name"] == "Get Job"
    )
    assert "{{jobId}}" in get_job_request["request"]["url"]["raw"]
    assert get_job_request["event"]

    studio_folder = next(item for item in collection["item"] if item["name"] == "Studio")
    create_configuration_request = next(
        item for item in studio_folder["item"] if item["name"] == "Create Configuration"
    )
    assert "{{patternId}}" in create_configuration_request["request"]["body"]["raw"]
    assert "{{entityId}}" in create_configuration_request["request"]["body"]["raw"]

    image_folder = next(item for item in collection["item"] if item["name"] == "Image Workflows")
    transform_job_request = next(
        item for item in image_folder["item"] if item["name"] == "Transform Image Job"
    )
    assert "{{jobId}}" in transform_job_request["request"]["body"]["raw"]
    assert "{{findingId}}" in transform_job_request["request"]["body"]["raw"]

    analyze_image_request = next(
        item for item in image_folder["item"] if item["name"] == "Analyze Image"
    )
    manifest_field = next(
        item
        for item in analyze_image_request["request"]["body"]["formdata"]
        if item["key"] == "manifest_json"
    )
    assert '"detect_text": true' in manifest_field["value"]

    structured_folder = next(
        item for item in collection["item"] if item["name"] == "Structured Workflows"
    )
    structured_analyze_request = next(
        item for item in structured_folder["item"] if item["name"] == "Analyze Structured"
    )
    assert '"data"' in structured_analyze_request["request"]["body"]["raw"]
    assert structured_analyze_request["event"]

    structured_transform_job_request = next(
        item for item in structured_folder["item"] if item["name"] == "Transform Structured Job"
    )
    assert "{{jobId}}" in structured_transform_job_request["request"]["body"]["raw"]
    assert "{{findingId}}" in structured_transform_job_request["request"]["body"]["raw"]

    document_folder = next(
        item for item in collection["item"] if item["name"] == "Document Workflows"
    )
    analyze_document_request = next(
        item for item in document_folder["item"] if item["name"] == "Analyze Document"
    )
    document_manifest_field = next(
        item
        for item in analyze_document_request["request"]["body"]["formdata"]
        if item["key"] == "manifest_json"
    )
    assert '"persist_job": true' in document_manifest_field["value"]
    assert analyze_document_request["event"]

    transform_document_job_request = next(
        item for item in document_folder["item"] if item["name"] == "Transform Document Job"
    )
    document_transform_manifest_field = next(
        item
        for item in transform_document_job_request["request"]["body"]["formdata"]
        if item["key"] == "manifest_json"
    )
    assert "{{jobId}}" in document_transform_manifest_field["value"]
    assert "{{findingId}}" in document_transform_manifest_field["value"]
