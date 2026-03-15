"""Helpers for output-intent policy enforcement and metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from obsura_api.domain.enums import (
    FindingSource,
    OutputIntent,
    ShareArtifactChannel,
    ShareArtifactKind,
    TransformationMode,
)
from obsura_api.domain.errors import UnprocessableContentError
from obsura_api.domain.sharing import ShareArtifactSummary, SharePolicySummary
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord

SAFE_SHARE_TEXT_NOTE = (
    "safe_share returns transformed text content rather than visually obscured text."
)
SAFE_SHARE_IMAGE_TEXT_NOTE = (
    "safe_share does not allow blur or pixelation for OCR or text-derived image findings."
)
CSV_EXPORT_NOTE = "Use output_csv for spreadsheet-safe export and external sharing."
CSV_PREVIEW_NOTE = "Use output_rows for review UI only."
PRESENTATION_ONLY_TEXT_IMAGE_MODES = {
    TransformationMode.BLUR,
    TransformationMode.PIXELATE,
}


@dataclass(frozen=True, slots=True)
class ResolvedImageShareTransform:
    """Resolved image transform after applying output-intent policy."""

    rule: TransformationRule
    security_rules_enforced: bool = False
    auto_adjusted: bool = False


def build_text_share_policy(output_intent: OutputIntent) -> SharePolicySummary:
    """Build policy metadata for text-bearing outputs."""

    if output_intent is OutputIntent.SAFE_SHARE:
        return SharePolicySummary(
            output_intent=output_intent,
            security_rules_enforced=True,
            notes=[SAFE_SHARE_TEXT_NOTE],
        )
    return SharePolicySummary(output_intent=output_intent)


def build_image_share_policy(
    output_intent: OutputIntent,
    *,
    security_rules_enforced: bool,
    auto_adjusted: bool,
) -> SharePolicySummary:
    """Build policy metadata for image outputs."""

    notes: list[str] = []
    if security_rules_enforced:
        notes.append(SAFE_SHARE_IMAGE_TEXT_NOTE)
    return SharePolicySummary(
        output_intent=output_intent,
        security_rules_enforced=security_rules_enforced,
        auto_adjusted=auto_adjusted,
        notes=notes,
    )


def share_metadata(
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
    artifact: ShareArtifactSummary | None = None,
) -> dict[str, object]:
    """Serialize share metadata for persisted output records."""

    metadata: dict[str, object] = {
        "output_intent": output_intent.value,
        "share_policy": share_policy.model_dump(mode="json"),
    }
    if artifact is not None:
        metadata["artifact"] = artifact.model_dump(
            mode="json",
            exclude={"output_file_path", "media_url"},
            exclude_none=True,
        )
    return metadata


def build_text_artifact(
    *,
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
    filename: str = "obsura-output.txt",
    primary: bool = True,
) -> ShareArtifactSummary:
    """Build the primary artifact descriptor for text-like outputs."""

    return ShareArtifactSummary(
        name="output_text",
        kind=ShareArtifactKind.TEXT,
        channel=ShareArtifactChannel.INLINE,
        intended_use=output_intent,
        share_ready=output_intent is OutputIntent.SAFE_SHARE,
        primary=primary,
        filename=filename,
        notes=list(share_policy.notes),
    )


def build_structured_artifact(
    *,
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
    primary: bool = True,
) -> ShareArtifactSummary:
    """Build the primary artifact descriptor for structured JSON outputs."""

    return ShareArtifactSummary(
        name="output_data",
        kind=ShareArtifactKind.JSON,
        channel=ShareArtifactChannel.INLINE,
        intended_use=output_intent,
        share_ready=output_intent is OutputIntent.SAFE_SHARE,
        primary=primary,
        filename="obsura-output.json",
        notes=list(share_policy.notes),
    )


def build_document_artifact(
    *,
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
    primary: bool = True,
) -> ShareArtifactSummary:
    """Build the primary artifact descriptor for document text outputs."""

    return ShareArtifactSummary(
        name="output_text",
        kind=ShareArtifactKind.TEXT,
        channel=ShareArtifactChannel.INLINE,
        intended_use=output_intent,
        share_ready=output_intent is OutputIntent.SAFE_SHARE,
        primary=primary,
        filename="obsura-document.txt",
        notes=list(share_policy.notes),
    )


def build_csv_export_artifact(
    *,
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
    primary: bool,
) -> ShareArtifactSummary:
    """Build the downloadable CSV export artifact descriptor."""

    notes = list(share_policy.notes)
    if CSV_EXPORT_NOTE not in notes:
        notes.append(CSV_EXPORT_NOTE)
    return ShareArtifactSummary(
        name="output_csv",
        kind=ShareArtifactKind.CSV_EXPORT,
        channel=ShareArtifactChannel.DOWNLOAD,
        intended_use=OutputIntent.SAFE_SHARE,
        share_ready=True,
        primary=primary,
        filename="obsura-output.csv",
        notes=notes,
    )


def build_csv_preview_artifact(*, primary: bool) -> ShareArtifactSummary:
    """Build the inline CSV preview artifact descriptor."""

    return ShareArtifactSummary(
        name="output_rows",
        kind=ShareArtifactKind.TABLE_PREVIEW,
        channel=ShareArtifactChannel.INLINE,
        intended_use=OutputIntent.PREVIEW,
        share_ready=False,
        primary=primary,
        notes=[CSV_PREVIEW_NOTE],
    )


def build_csv_response_artifacts(
    *,
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
) -> list[ShareArtifactSummary]:
    """Build response artifact descriptors for CSV transforms."""

    preview_artifact = build_csv_preview_artifact(primary=output_intent is OutputIntent.PREVIEW)
    export_artifact = build_csv_export_artifact(
        output_intent=output_intent,
        share_policy=share_policy,
        primary=output_intent is OutputIntent.SAFE_SHARE,
    )
    if output_intent is OutputIntent.SAFE_SHARE:
        return [export_artifact, preview_artifact]
    return [preview_artifact, export_artifact]


def build_image_artifact(
    *,
    output_intent: OutputIntent,
    share_policy: SharePolicySummary,
    output_file_path: str | None,
    media_url: str | None,
    primary: bool = True,
) -> ShareArtifactSummary:
    """Build the image artifact descriptor."""

    return ShareArtifactSummary(
        name="output_image",
        kind=ShareArtifactKind.IMAGE,
        channel=ShareArtifactChannel.MEDIA,
        intended_use=output_intent,
        share_ready=output_intent is OutputIntent.SAFE_SHARE,
        primary=primary,
        filename="obsura-output.png",
        output_file_path=output_file_path,
        media_url=media_url,
        notes=list(share_policy.notes),
    )


def artifact_from_metadata(
    metadata: Mapping[str, object] | None,
    *,
    output_file_path: str | None = None,
    media_url: str | None = None,
) -> ShareArtifactSummary | None:
    """Parse a persisted artifact descriptor and attach runtime path information."""

    if not metadata:
        return None
    raw_artifact = metadata.get("artifact")
    if not isinstance(raw_artifact, dict):
        return None
    artifact = ShareArtifactSummary.model_validate(raw_artifact)
    return artifact.model_copy(
        update={
            "output_file_path": output_file_path or artifact.output_file_path,
            "media_url": media_url or artifact.media_url,
        }
    )


def resolve_image_transform_for_output_intent(
    *,
    finding: FindingRecord,
    finding_rule: TransformationRule | None,
    default_rule: TransformationRule | None,
    output_intent: OutputIntent,
) -> ResolvedImageShareTransform:
    """Resolve the final image rule for one finding under the requested output intent."""

    resolved_rule = finding_rule or default_rule
    explicit_rule = resolved_rule is not None
    if resolved_rule is None:
        resolved_rule = TransformationRule(mode=TransformationMode.BLUR)

    if output_intent is not OutputIntent.SAFE_SHARE or not is_text_derived_image_finding(finding):
        return ResolvedImageShareTransform(rule=resolved_rule)

    if resolved_rule.mode in PRESENTATION_ONLY_TEXT_IMAGE_MODES:
        if explicit_rule:
            raise UnprocessableContentError(
                "safe_share does not allow blur or pixelation for OCR or "
                "text-derived findings. Use overlay or another destructive visual transform.",
            )
        return ResolvedImageShareTransform(
            rule=TransformationRule(mode=TransformationMode.OVERLAY),
            security_rules_enforced=True,
            auto_adjusted=True,
        )

    return ResolvedImageShareTransform(
        rule=resolved_rule,
        security_rules_enforced=True,
    )


def is_text_derived_image_finding(finding: FindingRecord) -> bool:
    """Return whether an image finding originates from detected text."""

    return finding.source is FindingSource.OCR or bool(finding.metadata.get("ocr_text_hash"))
