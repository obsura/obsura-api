from __future__ import annotations

from sqlalchemy import text

import pytest

from obsura_api.core.settings import Settings
from obsura_api.db import session as session_module
from obsura_api.db.migrations import create_alembic_config, get_head_revision, get_schema_state


def test_create_alembic_config_uses_packaged_scripts() -> None:
    config = create_alembic_config("sqlite:///./example.db")

    assert config.get_main_option("sqlalchemy.url") == "sqlite:///./example.db"
    assert config.get_main_option("script_location").replace("\\", "/").endswith(
        "src/obsura_api/db/alembic"
    )
    assert get_head_revision("sqlite:///./example.db") == "ebbb78f282b7"


def test_ensure_database_schema_rejects_wrong_revision(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'revision-mismatch.db').as_posix()}",
        auto_create_schema=False,
        _env_file=None,
    )
    engine = session_module.create_engine_from_settings(settings)
    session_module.upgrade_database_from_settings(settings)

    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'deadbeef'"))

    schema_state = get_schema_state(engine, settings.database_url)
    assert schema_state.current_revision == "deadbeef"
    assert schema_state.is_at_head is False

    with pytest.raises(RuntimeError, match="Current revision: deadbeef"):
        session_module.ensure_database_schema(engine, settings=settings)
