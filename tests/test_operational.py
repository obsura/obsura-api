from __future__ import annotations

from obsura_api.core.settings import Settings
from obsura_api.db.migrations import get_head_revision
from obsura_api.services.storage import StorageService


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


def test_storage_service_uses_safe_relative_references(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'obsura.db'}",
        storage_root=tmp_path / "storage",
        _env_file=None,
    )
    storage = StorageService(settings)

    upload_path = storage.save_upload(b"abc", "evidence.PNG")
    output_reference = storage.storage_reference_for(upload_path)

    assert upload_path.is_absolute()
    assert output_reference.startswith("uploads/")
    assert storage.resolve_stored_path(output_reference) == upload_path
