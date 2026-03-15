"""Share policy request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from obsura_api.domain.enums import OutputIntent


class SharePolicySummary(BaseModel):
    """How the API interpreted a transform request for sharing."""

    output_intent: OutputIntent = OutputIntent.PREVIEW
    security_rules_enforced: bool = False
    auto_adjusted: bool = False
    notes: list[str] = Field(default_factory=list)
