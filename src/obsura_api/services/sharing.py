"""Helpers for output-intent policy enforcement and metadata."""

from __future__ import annotations

from dataclasses import dataclass

from obsura_api.domain.enums import FindingSource, OutputIntent, TransformationMode
from obsura_api.domain.errors import UnprocessableContentError
from obsura_api.domain.sharing import SharePolicySummary
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord

SAFE_SHARE_TEXT_NOTE = (
    "safe_share returns transformed text content rather than visually obscured text."
)
SAFE_SHARE_IMAGE_TEXT_NOTE = (
    "safe_share does not allow blur or pixelation for OCR or text-derived image findings."
)
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
) -> dict[str, object]:
    """Serialize share metadata for persisted output records."""

    return {
        "output_intent": output_intent.value,
        "share_policy": share_policy.model_dump(mode="json"),
    }


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
