from __future__ import annotations

from obsura_api.app import create_app
from obsura_api.tools.api_artifacts import build_postman_collection


def test_postman_collection_uses_chained_variables() -> None:
    collection = build_postman_collection(create_app().openapi())

    variables = {item["key"] for item in collection["variable"]}
    assert {"baseUrl", "patternId", "configurationId", "jobId", "findingId"} <= variables

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
