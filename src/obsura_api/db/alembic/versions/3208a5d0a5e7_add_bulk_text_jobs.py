"""add_bulk_text_jobs"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "3208a5d0a5e7"
down_revision = "ebbb78f282b7"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_table_if_exists(table_name: str) -> None:
    if _has_table(table_name):
        op.drop_table(table_name)


def _content_type_enum() -> sa.Enum:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(
            "TEXT",
            "STRUCTURED_TEXT",
            "SCREENSHOT",
            "IMAGE",
            name="contenttype",
            create_type=False,
        )
    return sa.Enum("TEXT", "STRUCTURED_TEXT", "SCREENSHOT", "IMAGE", name="contenttype")


def upgrade() -> None:
    if not _has_table("bulk_jobs"):
        op.create_table(
            "bulk_jobs",
            sa.Column("title", sa.String(length=160), nullable=True),
            sa.Column(
                "content_type",
                _content_type_enum(),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.Enum("COMPLETED", "PARTIAL_FAILURE", "FAILED", name="bulkjobstatus"),
                nullable=False,
            ),
            sa.Column("item_count", sa.Integer(), nullable=False),
            sa.Column("success_count", sa.Integer(), nullable=False),
            sa.Column("failure_count", sa.Integer(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_bulk_jobs_status"), "bulk_jobs", ["status"])

    if not _has_table("bulk_job_items"):
        op.create_table(
            "bulk_job_items",
            sa.Column("bulk_job_id", sa.String(length=36), nullable=False),
            sa.Column("item_index", sa.Integer(), nullable=False),
            sa.Column("client_item_id", sa.String(length=120), nullable=True),
            sa.Column("title", sa.String(length=160), nullable=True),
            sa.Column(
                "status",
                sa.Enum("SUCCEEDED", "FAILED", name="bulkjobitemstatus"),
                nullable=False,
            ),
            sa.Column("job_id", sa.String(length=36), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["bulk_job_id"], ["bulk_jobs.id"]),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("bulk_job_id", "item_index", name="uq_bulk_job_items_bulk_job_id_item_index"),
            sa.UniqueConstraint("job_id"),
        )
    _create_index_if_missing(op.f("ix_bulk_job_items_bulk_job_id"), "bulk_job_items", ["bulk_job_id"])
    _create_index_if_missing(op.f("ix_bulk_job_items_job_id"), "bulk_job_items", ["job_id"])


def downgrade() -> None:
    _drop_index_if_exists(op.f("ix_bulk_job_items_job_id"), "bulk_job_items")
    _drop_index_if_exists(op.f("ix_bulk_job_items_bulk_job_id"), "bulk_job_items")
    _drop_table_if_exists("bulk_job_items")
    _drop_index_if_exists(op.f("ix_bulk_jobs_status"), "bulk_jobs")
    _drop_table_if_exists("bulk_jobs")
