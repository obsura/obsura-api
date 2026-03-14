"""initial_schema_baseline"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "ebbb78f282b7"
down_revision = None
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


def upgrade() -> None:
    if not _has_table("custom_entities"):
        op.create_table(
            "custom_entities",
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=80), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("detection_definitions", sa.JSON(), nullable=False),
            sa.Column("transformation", sa.JSON(), nullable=True),
            sa.Column("scope", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_custom_entities_category"), "custom_entities", ["category"])
    _create_index_if_missing(op.f("ix_custom_entities_name"), "custom_entities", ["name"])

    if not _has_table("jobs"):
        op.create_table(
            "jobs",
            sa.Column("title", sa.String(length=160), nullable=True),
            sa.Column(
                "status",
                sa.Enum("ANALYZED", "REVIEWED", "TRANSFORMED", name="jobstatus"),
                nullable=False,
            ),
            sa.Column(
                "content_type",
                sa.Enum(
                    "TEXT",
                    "STRUCTURED_TEXT",
                    "DOCUMENT",
                    "CSV",
                    "SCREENSHOT",
                    "IMAGE",
                    name="contenttype",
                ),
                nullable=False,
            ),
            sa.Column("source_text", sa.Text(), nullable=True),
            sa.Column("source_file_path", sa.String(length=500), nullable=True),
            sa.Column("pattern_ids", sa.JSON(), nullable=False),
            sa.Column("custom_entity_ids", sa.JSON(), nullable=False),
            sa.Column("configuration_ids", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("patterns"):
        op.create_table(
            "patterns",
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=80), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("matcher", sa.JSON(), nullable=False),
            sa.Column("transformation", sa.JSON(), nullable=True),
            sa.Column("scope", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_patterns_category"), "patterns", ["category"])
    _create_index_if_missing(op.f("ix_patterns_name"), "patterns", ["name"])

    if not _has_table("studio_configurations"):
        op.create_table(
            "studio_configurations",
            sa.Column(
                "kind",
                sa.Enum("PACK", "PROFILE", "PRESET", name="configurationkind"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=80), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("pattern_ids", sa.JSON(), nullable=False),
            sa.Column("custom_entity_ids", sa.JSON(), nullable=False),
            sa.Column("default_text_transformation", sa.JSON(), nullable=True),
            sa.Column("default_image_transformation", sa.JSON(), nullable=True),
            sa.Column("face_preferences", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        op.f("ix_studio_configurations_category"),
        "studio_configurations",
        ["category"],
    )
    _create_index_if_missing(
        op.f("ix_studio_configurations_kind"),
        "studio_configurations",
        ["kind"],
    )
    _create_index_if_missing(
        op.f("ix_studio_configurations_name"),
        "studio_configurations",
        ["name"],
    )

    if not _has_table("job_findings"):
        op.create_table(
            "job_findings",
            sa.Column("job_id", sa.String(length=36), nullable=False),
            sa.Column(
                "source",
                sa.Enum("BUILT_IN", "CUSTOM", "MANUAL", "FACE", "OCR", name="findingsource"),
                nullable=False,
            ),
            sa.Column(
                "kind",
                sa.Enum(
                    "TEXT_SPAN",
                    "IMAGE_REGION",
                    "FACE_REGION",
                    "FACE_SUBREGION",
                    name="findingkind",
                ),
                nullable=False,
            ),
            sa.Column("entity_type", sa.String(length=120), nullable=False),
            sa.Column("entity_name", sa.String(length=120), nullable=True),
            sa.Column("start_index", sa.Integer(), nullable=True),
            sa.Column("end_index", sa.Integer(), nullable=True),
            sa.Column("region", sa.JSON(), nullable=True),
            sa.Column("matched_text_preview", sa.String(length=255), nullable=True),
            sa.Column("matched_text_hash", sa.String(length=64), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column(
                "decision",
                sa.Enum("PENDING", "APPROVED", "REJECTED", name="reviewdecision"),
                nullable=False,
            ),
            sa.Column("transformation", sa.JSON(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_job_findings_job_id"), "job_findings", ["job_id"])
    _create_index_if_missing(
        op.f("ix_job_findings_matched_text_hash"),
        "job_findings",
        ["matched_text_hash"],
    )

    if not _has_table("job_outputs"):
        op.create_table(
            "job_outputs",
            sa.Column("job_id", sa.String(length=36), nullable=False),
            sa.Column(
                "content_type",
                sa.Enum(
                    "TEXT",
                    "STRUCTURED_TEXT",
                    "DOCUMENT",
                    "CSV",
                    "SCREENSHOT",
                    "IMAGE",
                    name="contenttype",
                ),
                nullable=False,
            ),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("output_file_path", sa.String(length=500), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_job_outputs_job_id"), "job_outputs", ["job_id"])


def downgrade() -> None:
    _drop_index_if_exists(op.f("ix_job_outputs_job_id"), "job_outputs")
    _drop_table_if_exists("job_outputs")
    _drop_index_if_exists(op.f("ix_job_findings_matched_text_hash"), "job_findings")
    _drop_index_if_exists(op.f("ix_job_findings_job_id"), "job_findings")
    _drop_table_if_exists("job_findings")
    _drop_index_if_exists(op.f("ix_studio_configurations_name"), "studio_configurations")
    _drop_index_if_exists(op.f("ix_studio_configurations_kind"), "studio_configurations")
    _drop_index_if_exists(op.f("ix_studio_configurations_category"), "studio_configurations")
    _drop_table_if_exists("studio_configurations")
    _drop_index_if_exists(op.f("ix_patterns_name"), "patterns")
    _drop_index_if_exists(op.f("ix_patterns_category"), "patterns")
    _drop_table_if_exists("patterns")
    _drop_table_if_exists("jobs")
    _drop_index_if_exists(op.f("ix_custom_entities_name"), "custom_entities")
    _drop_index_if_exists(op.f("ix_custom_entities_category"), "custom_entities")
    _drop_table_if_exists("custom_entities")
