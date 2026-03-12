"""SQLAlchemy models for persistent Obsura API state."""

from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from obsura_api.db.base import Base, TimestampedUUIDMixin
from obsura_api.domain.enums import (
    BulkJobItemStatus,
    BulkJobStatus,
    ConfigurationKind,
    ContentType,
    FindingKind,
    FindingSource,
    JobStatus,
    ReviewDecision,
)


class Pattern(TimestampedUUIDMixin, Base):
    """Saved pattern with one matcher and optional transformation."""

    __tablename__ = "patterns"

    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    matcher: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    transformation: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)


class CustomEntity(TimestampedUUIDMixin, Base):
    """Saved custom entity composed of one or more detection definitions."""

    __tablename__ = "custom_entities"

    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detection_definitions: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    transformation: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)


class StudioConfiguration(TimestampedUUIDMixin, Base):
    """Reusable pack, profile, or preset."""

    __tablename__ = "studio_configurations"

    kind: Mapped[ConfigurationKind] = mapped_column(
        Enum(ConfigurationKind),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pattern_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    custom_entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    default_text_transformation: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    default_image_transformation: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    face_preferences: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    extra_data: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )


class BulkJob(TimestampedUUIDMixin, Base):
    """Persisted parent resource for one ordered bulk text submission."""

    __tablename__ = "bulk_jobs"

    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), nullable=False)
    status: Mapped[BulkJobStatus] = mapped_column(Enum(BulkJobStatus), index=True, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    items: Mapped[list["BulkJobItem"]] = relationship(
        back_populates="bulk_job",
        cascade="all, delete-orphan",
        order_by="BulkJobItem.item_index",
    )


class Job(TimestampedUUIDMixin, Base):
    """Persisted workflow job."""

    __tablename__ = "jobs"

    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pattern_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    custom_entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    configuration_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)

    findings: Mapped[list["JobFinding"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    outputs: Mapped[list["JobOutput"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    bulk_item: Mapped["BulkJobItem | None"] = relationship(back_populates="job")


class BulkJobItem(TimestampedUUIDMixin, Base):
    """Stored result for one item inside a bulk text submission."""

    __tablename__ = "bulk_job_items"
    __table_args__ = (
        UniqueConstraint("bulk_job_id", "item_index", name="uq_bulk_job_items_bulk_job_id_item_index"),
    )

    bulk_job_id: Mapped[str] = mapped_column(ForeignKey("bulk_jobs.id"), index=True, nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    client_item_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[BulkJobItemStatus] = mapped_column(
        Enum(BulkJobItemStatus),
        nullable=False,
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"),
        index=True,
        nullable=True,
        unique=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)

    bulk_job: Mapped[BulkJob] = relationship(back_populates="items")
    job: Mapped[Job | None] = relationship(back_populates="bulk_item")


class JobFinding(TimestampedUUIDMixin, Base):
    """One reviewable finding stored under a job."""

    __tablename__ = "job_findings"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=False)
    source: Mapped[FindingSource] = mapped_column(Enum(FindingSource), nullable=False)
    kind: Mapped[FindingKind] = mapped_column(Enum(FindingKind), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    start_index: Mapped[int | None] = mapped_column(nullable=True)
    end_index: Mapped[int | None] = mapped_column(nullable=True)
    region: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    matched_text_preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    decision: Mapped[ReviewDecision] = mapped_column(
        Enum(ReviewDecision),
        nullable=False,
        default=ReviewDecision.PENDING,
    )
    transformation: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    job: Mapped[Job] = relationship(back_populates="findings")


class JobOutput(TimestampedUUIDMixin, Base):
    """Stored output for a job."""

    __tablename__ = "job_outputs"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=False)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    job: Mapped[Job] = relationship(back_populates="outputs")
