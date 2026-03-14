from __future__ import annotations

from obsura_api.core.settings import Settings
from obsura_api.db.migrations import get_head_revision
from obsura_api.services.storage import StorageService


def test_friendly_api_root_returns_public_metadata(client) -> None:
    response = client.get(
        "/",
        headers={
            "Host": "api.obsura.one",
            "X-Forwarded-Proto": "https",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "name": "Obsura API",
        "status": "ok",
        "docs_url": "https://api.obsura.one/docs",
        "openapi_url": "https://api.obsura.one/openapi.json",
        "version": "v0.1.0",
        "ocr_available": False,
        "face_detection_available": False,
        "pii_available": False,
    }


def test_api_alias_returns_same_friendly_metadata(client) -> None:
    headers = {
        "Host": "api.obsura.one",
        "X-Forwarded-Proto": "https",
    }

    root_response = client.get("/", headers=headers)
    api_response = client.get("/api", headers=headers)

    assert api_response.status_code == 200
    assert api_response.json() == root_response.json()


def test_ready_and_version_endpoints(client) -> None:
    ready_response = client.get("/api/v1/ready")
    assert ready_response.status_code == 200
    ready_body = ready_response.json()
    assert ready_body["success"] is True
    assert ready_body["data"]["status"] == "ready"

    version_response = client.get("/api/v1/version")
    assert version_response.status_code == 200
    version_body = version_response.json()
    assert version_body["success"] is True
    assert version_body["data"]["name"] == "Obsura API"
    assert version_body["data"]["version"] == "0.1.0"
    assert version_body["data"]["database_backend"].startswith("sqlite")
    expected_head = get_head_revision("sqlite:///./example.db")
    assert version_body["data"]["schema_revision"] == expected_head
    assert version_body["data"]["schema_head"] == expected_head
    assert version_body["data"]["pii_backend"] == "noop-pii-detector"
    assert version_body["data"]["text_anonymizer_backend"] == "native-text-anonymizer"
    assert version_body["data"]["pii_languages"] == []
    assert version_body["data"]["pii_custom_recognizers"] is False
    assert version_body["data"]["text_hash_supported"] is False
    assert version_body["data"]["ocr_available"] is False
    assert version_body["data"]["face_detection_available"] is False
    assert version_body["data"]["pii_available"] is False


def test_cors_preflight_allows_local_frontend(client) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-headers"] == "Authorization"


def test_storage_service_uses_safe_relative_references(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'obsura.db'}",
        storage_root=tmp_path / "storage",
        _env_file=None,
    )
    storage = StorageService(settings)

    upload_reference = storage.save_upload(b"abc", "evidence.PNG")
    output_reference = storage.storage_reference_for(upload_reference)

    assert output_reference.startswith("uploads/")
    assert storage.read_stored_bytes(output_reference) == b"abc"
