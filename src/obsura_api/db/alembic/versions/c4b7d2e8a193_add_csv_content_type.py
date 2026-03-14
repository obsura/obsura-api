"""add_csv_content_type"""

from __future__ import annotations

from alembic import op

revision = "c4b7d2e8a193"
down_revision = "b91e0c9f4c12"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")


def upgrade() -> None:
    _add_enum_value_if_missing("contenttype", "CSV")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally left in place.
    pass
