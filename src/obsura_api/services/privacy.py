"""Sensitive-data scrubbing and persistence sanitization helpers."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from obsura_api.db.models import Job, JobFinding, JobOutput

SAFE_FINDING_METADATA_KEYS = {
    "csv_cell_character_count",
    "csv_cell_hash",
    "csv_column_index",
    "csv_column_name",
    "csv_delimiter",
    "csv_has_header",
    "csv_kind",
    "csv_quotechar",
    "csv_row_number",
    "document_kind",
    "document_page_number",
    "document_page_label",
    "document_page_text_hash",
    "document_page_character_count",
    "ocr_confidence",
    "ocr_detection_source",
    "ocr_text_hash",
    "ocr_token_count",
    "pii_confidence_profile",
    "pii_confidence_threshold",
    "pii_detection_reason",
    "pii_detector_language",
    "structured_path",
    "structured_path_tokens",
    "structured_value_kind",
}


def sanitize_persisted_finding_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    """Keep only non-sensitive metadata fields that are safe to retain."""

    if not metadata:
        return {}
    return {key: value for key, value in metadata.items() if key in SAFE_FINDING_METADATA_KEYS}


def scrub_persisted_sensitive_data(session: Session) -> dict[str, int]:
    """Remove historically persisted sensitive source and output content."""

    scrubbed_jobs = (
        session.execute(
            update(Job).values(
                source_text=None,
                source_file_path=None,
            ),
        ).rowcount
        or 0
    )
    scrubbed_outputs = (
        session.execute(
            update(JobOutput).values(
                output_text=None,
                output_file_path=None,
            ),
        ).rowcount
        or 0
    )

    scrubbed_findings = 0
    findings = session.query(JobFinding).all()
    for finding in findings:
        sanitized_metadata = sanitize_persisted_finding_metadata(finding.extra_data)
        if finding.matched_text_preview is None and sanitized_metadata == (
            finding.extra_data or {}
        ):
            continue
        finding.matched_text_preview = None
        finding.extra_data = sanitized_metadata
        scrubbed_findings += 1

    session.commit()
    return {
        "jobs": scrubbed_jobs,
        "outputs": scrubbed_outputs,
        "findings": scrubbed_findings,
    }
