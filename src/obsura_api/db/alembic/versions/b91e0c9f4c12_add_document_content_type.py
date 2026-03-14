"""add_document_content_type"""

from __future__ import annotations

from alembic import op

revision = "b91e0c9f4c12"
down_revision = "7853e355f826"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")


def upgrade() -> None:
    _add_enum_value_if_missing("contenttype", "DOCUMENT")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally left in place.
    pass
