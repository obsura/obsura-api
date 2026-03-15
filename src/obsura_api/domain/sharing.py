"""Share policy and artifact request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from obsura_api.domain.enums import OutputIntent, ShareArtifactChannel, ShareArtifactKind


class SharePolicySummary(BaseModel):
    """How the API interpreted a transform request for sharing."""

    output_intent: OutputIntent = OutputIntent.PREVIEW
    security_rules_enforced: bool = False
    auto_adjusted: bool = False
    notes: list[str] = Field(default_factory=list)


class ShareArtifactSummary(BaseModel):
    """One explicit artifact produced for preview or sharing."""

    name: str
    kind: ShareArtifactKind
    channel: ShareArtifactChannel
    intended_use: OutputIntent
    share_ready: bool = False
    primary: bool = False
    filename: str | None = None
    output_file_path: str | None = None
    media_url: str | None = None
    notes: list[str] = Field(default_factory=list)
