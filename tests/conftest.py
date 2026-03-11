from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsura_api.app import create_app
from obsura_api.core.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'obsura.db'}",
        storage_root=tmp_path / "storage",
        auto_create_schema=True,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

