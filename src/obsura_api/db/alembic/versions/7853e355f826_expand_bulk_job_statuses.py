"""expand_bulk_job_statuses"""

from __future__ import annotations

from alembic import op

revision = "7853e355f826"
down_revision = "3208a5d0a5e7"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")


def upgrade() -> None:
    for value in ("PARTIALLY_REVIEWED", "REVIEWED", "PARTIALLY_TRANSFORMED", "TRANSFORMED"):
        _add_enum_value_if_missing("bulkjobstatus", value)
    for value in ("REVIEWED", "TRANSFORMED"):
        _add_enum_value_if_missing("bulkjobitemstatus", value)


def downgrade() -> None:
    # PostgreSQL enum values are intentionally left in place.
    pass
