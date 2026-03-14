"""Shared service-layer helpers."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from obsura_api.domain.enums import ReviewDecision
from obsura_api.domain.workflows import FindingRecord


def hash_value(value: str) -> str:
    """Return a stable hash for a sensitive value without storing it raw."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def preview_value(value: str, keep: int = 2) -> str:
    """Return a short masked preview for review surfaces and job history."""

    if len(value) <= keep * 2:
        return value[0] + ("*" * max(len(value) - 2, 0)) + value[-1] if len(value) > 1 else value
    return f"{value[:keep]}{'*' * max(len(value) - keep * 2, 1)}{value[-keep:]}"


def normalize_token(value: str) -> str:
    """Convert a label into a stable alias prefix."""

    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    return normalized or "SENSITIVE_VALUE"


def unique_ids(*values: Iterable[str]) -> list[str]:
    """Merge iterables while preserving first-seen order."""

    merged: list[str] = []
    seen: set[str] = set()
    for iterable in values:
        for item in iterable:
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def summarize_findings(findings: list[FindingRecord]) -> dict[str, int]:
    """Summarize decision counts for a finding collection."""

    pending = sum(1 for item in findings if item.decision is ReviewDecision.PENDING)
    approved = sum(1 for item in findings if item.decision is ReviewDecision.APPROVED)
    rejected = sum(1 for item in findings if item.decision is ReviewDecision.REJECTED)
    return {
        "total": len(findings),
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
    }
