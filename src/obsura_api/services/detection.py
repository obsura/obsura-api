"""Text detection workflows for built-in and user-defined rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobFinding
from obsura_api.domain.enums import (
    ContentType,
    FindingKind,
    FindingSource,
    JobStatus,
    MatcherKind,
    TransformationMode,
)
from obsura_api.domain.studio import PatternMatcherDefinition
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord, ManualTextSpan, TextAnalysisRequest, TextAnalysisResponse
from obsura_api.services.studio import StudioService
from obsura_api.services.utils import hash_value, preview_value, summarize_findings, unique_ids


@dataclass(slots=True)
class BuiltInPattern:
    """A built-in regex detector."""

    entity_type: str
    entity_name: str
    pattern: re.Pattern[str]
    transformation: TransformationRule
    group_index: int | None = None


BUILT_IN_PATTERNS: list[BuiltInPattern] = [
    BuiltInPattern(
        entity_type="IP_ADDRESS",
        entity_name="IPv4 address",
        pattern=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="IP_ADDRESS",
        ),
    ),
    BuiltInPattern(
        entity_type="EMAIL_ADDRESS",
        entity_name="Email address",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="EMAIL",
        ),
    ),
    BuiltInPattern(
        entity_type="URL",
        entity_name="URL",
        pattern=re.compile(r"\bhttps?://[^\s/$.?#].[^\s]*", re.IGNORECASE),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="URL",
        ),
    ),
    BuiltInPattern(
        entity_type="JWT",
        entity_name="JSON Web Token",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="JWT",
        ),
    ),
    BuiltInPattern(
        entity_type="AWS_ACCESS_KEY_ID",
        entity_name="AWS access key ID",
        pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="AWS_ACCESS_KEY",
        ),
    ),
    BuiltInPattern(
        entity_type="GITHUB_TOKEN",
        entity_name="GitHub token",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="GITHUB_TOKEN",
        ),
    ),
    BuiltInPattern(
        entity_type="BEARER_TOKEN",
        entity_name="Bearer token",
        pattern=re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._-]{16,})\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="BEARER_TOKEN",
        ),
        group_index=1,
    ),
    BuiltInPattern(
        entity_type="SECRET_VALUE",
        entity_name="Secret assignment value",
        pattern=re.compile(
            r"(?im)\b(?:api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"]?([^\s'\"`]{4,})",
        ),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="SECRET_VALUE",
        ),
        group_index=1,
    ),
    BuiltInPattern(
        entity_type="ENV_SECRET",
        entity_name="Environment secret value",
        pattern=re.compile(
            r"(?im)^(?:export\s+)?[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*['\"]?([^\n'\"`]+)",
        ),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="ENV_SECRET",
        ),
        group_index=1,
    ),
    BuiltInPattern(
        entity_type="SSH_PUBLIC_KEY",
        entity_name="SSH public key",
        pattern=re.compile(r"\bssh-(?:rsa|ed25519|ecdsa)\s+[A-Za-z0-9+/=]+(?:\s+[^\s]+)?"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="SSH_KEY",
        ),
    ),
    BuiltInPattern(
        entity_type="PRIVATE_KEY",
        entity_name="Private key block",
        pattern=re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.MULTILINE,
        ),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="PRIVATE_KEY",
        ),
    ),
    BuiltInPattern(
        entity_type="HOSTNAME",
        entity_name="Hostname or domain",
        pattern=re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b"),
        transformation=TransformationRule(
            mode=TransformationMode.SEMANTIC,
            semantic_label="HOSTNAME",
        ),
    ),
]


class TextDetectionService:
    """Analyze text content into reviewable findings and optional job records."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.studio = StudioService(session)

    def analyze(self, request: TextAnalysisRequest) -> TextAnalysisResponse:
        (
            patterns,
            entities,
            pattern_ids,
            custom_entity_ids,
            configuration_ids,
            default_transformation,
        ) = self.resolve_detection_context(
            content_type=request.content_type,
            pattern_ids=request.pattern_ids,
            custom_entity_ids=request.custom_entity_ids,
            configuration_ids=request.configuration_ids,
            default_transformation=request.default_transformation,
        )
        findings = self.build_findings(
            content=request.content,
            content_type=request.content_type,
            apply_builtins=request.apply_builtins,
            exact_values=request.exact_values,
            manual_spans=request.manual_spans,
            patterns=patterns,
            entities=entities,
            default_transformation=default_transformation,
        )

        job_id: str | None = None
        if request.persist_job:
            persist_source = request.persist_source_content
            if persist_source is None:
                persist_source = self.settings.retain_source_content_by_default
            job_id = self.persist_analyzed_job(
                title=request.title,
                content_type=request.content_type,
                content=request.content if persist_source else None,
                pattern_ids=pattern_ids,
                custom_entity_ids=custom_entity_ids,
                configuration_ids=configuration_ids,
                findings=findings,
            )

        summary = summarize_findings(findings)
        return TextAnalysisResponse(job_id=job_id, findings=findings, summary=summary)

    def build_findings(
        self,
        *,
        content: str,
        content_type: ContentType,
        apply_builtins: bool,
        exact_values: list[str],
        manual_spans: list[ManualTextSpan],
        patterns: list[object],
        entities: list[object],
        default_transformation: TransformationRule | None,
    ) -> list[FindingRecord]:
        """Build transient findings for text content without persisting a job."""

        findings: list[FindingRecord] = []
        if apply_builtins:
            findings.extend(self._detect_built_ins(content, default_transformation))

        for pattern in patterns:
            matcher = PatternMatcherDefinition.model_validate(pattern.matcher)
            if content_type not in matcher.applies_to:
                continue
            transformation = self._coalesce_transformation(
                pattern.transformation,
                default_transformation,
            )
            findings.extend(
                self._detect_matcher(
                    content,
                    matcher,
                    source=FindingSource.CUSTOM,
                    entity_type=pattern.name,
                    entity_name=pattern.name,
                    transformation=transformation,
                ),
            )

        for entity in entities:
            transformation = self._coalesce_transformation(
                entity.transformation,
                default_transformation,
            )
            for definition in entity.detection_definitions:
                matcher = PatternMatcherDefinition.model_validate(definition)
                if content_type not in matcher.applies_to:
                    continue
                findings.extend(
                    self._detect_matcher(
                        content,
                        matcher,
                        source=FindingSource.CUSTOM,
                        entity_type=entity.name,
                        entity_name=entity.name,
                        transformation=transformation,
                    ),
                )

        for exact_value in exact_values:
            matcher = PatternMatcherDefinition(
                kind=MatcherKind.EXACT,
                value=exact_value,
                applies_to=[content_type],
            )
            findings.extend(
                self._detect_matcher(
                    content,
                    matcher,
                    source=FindingSource.MANUAL,
                    entity_type="EXACT_VALUE",
                    entity_name="Manual exact value",
                    transformation=default_transformation,
                ),
            )

        findings.extend(self._manual_findings(content, manual_spans))
        return self._deduplicate_findings(findings)

    def resolve_transient_detection_context(
        self,
        *,
        content_type: ContentType,
        pattern_ids: list[str],
        custom_entity_ids: list[str],
        configuration_ids: list[str],
        default_transformation: TransformationRule | None = None,
    ) -> tuple[list[object], list[object], TransformationRule | None]:
        """Resolve reusable detection inputs for transient text analysis."""

        patterns, entities, _, _, _, resolved_default = self.resolve_detection_context(
            content_type=content_type,
            pattern_ids=pattern_ids,
            custom_entity_ids=custom_entity_ids,
            configuration_ids=configuration_ids,
            default_transformation=default_transformation,
        )
        return patterns, entities, resolved_default

    def resolve_detection_context(
        self,
        *,
        content_type: ContentType,
        pattern_ids: list[str],
        custom_entity_ids: list[str],
        configuration_ids: list[str],
        default_transformation: TransformationRule | None,
    ) -> tuple[
        list[object],
        list[object],
        list[str],
        list[str],
        list[str],
        TransformationRule | None,
    ]:
        configurations = self.studio.resolve_configurations(configuration_ids)
        resolved_pattern_ids = unique_ids(
            pattern_ids,
            *(config.pattern_ids for config in configurations),
        )
        resolved_custom_entity_ids = unique_ids(
            custom_entity_ids,
            *(config.custom_entity_ids for config in configurations),
        )
        patterns = [item for item in self.studio.resolve_patterns(resolved_pattern_ids) if item.is_active]
        entities = [
            item
            for item in self.studio.resolve_custom_entities(resolved_custom_entity_ids)
            if item.is_active
        ]
        resolved_default = self._resolve_default_transformation(
            default_transformation,
            configurations,
        )
        _ = content_type
        return (
            patterns,
            entities,
            resolved_pattern_ids,
            resolved_custom_entity_ids,
            unique_ids(configuration_ids),
            resolved_default,
        )

    def _resolve_default_transformation(
        self,
        request_default: TransformationRule | None,
        configurations: list[object],
    ) -> TransformationRule | None:
        if request_default is not None:
            return request_default
        for config in configurations:
            if getattr(config, "default_text_transformation", None):
                return TransformationRule.model_validate(config.default_text_transformation)
        return None

    def _coalesce_transformation(
        self,
        raw_transformation: dict[str, object] | None,
        default_transformation: TransformationRule | None,
    ) -> TransformationRule | None:
        if raw_transformation:
            return TransformationRule.model_validate(raw_transformation)
        return default_transformation

    def _detect_built_ins(
        self,
        text: str,
        default_transformation: TransformationRule | None,
    ) -> list[FindingRecord]:
        findings: list[FindingRecord] = []
        for definition in BUILT_IN_PATTERNS:
            transformation = default_transformation or definition.transformation
            for match in definition.pattern.finditer(text):
                start_index = match.start(definition.group_index or 0)
                end_index = match.end(definition.group_index or 0)
                findings.append(
                    self._build_text_finding(
                        text=text,
                        start_index=start_index,
                        end_index=end_index,
                        source=FindingSource.BUILT_IN,
                        entity_type=definition.entity_type,
                        entity_name=definition.entity_name,
                        transformation=transformation,
                    ),
                )
        return findings

    def _detect_matcher(
        self,
        text: str,
        matcher: PatternMatcherDefinition,
        source: FindingSource,
        entity_type: str,
        entity_name: str,
        transformation: TransformationRule | None,
    ) -> list[FindingRecord]:
        findings: list[FindingRecord] = []
        if matcher.kind is MatcherKind.REGEX:
            flags = 0 if matcher.case_sensitive else re.IGNORECASE
            pattern = re.compile(matcher.value or "", flags)
            for match in pattern.finditer(text):
                findings.append(
                    self._build_text_finding(
                        text=text,
                        start_index=match.start(),
                        end_index=match.end(),
                        source=source,
                        entity_type=entity_type,
                        entity_name=entity_name,
                        transformation=transformation,
                    ),
                )
            return findings

        values = [matcher.value] if matcher.kind is MatcherKind.EXACT else matcher.values
        for raw_value in filter(None, values):
            escaped = re.escape(raw_value or "")
            flags = 0 if matcher.case_sensitive else re.IGNORECASE
            for match in re.finditer(escaped, text, flags):
                findings.append(
                    self._build_text_finding(
                        text=text,
                        start_index=match.start(),
                        end_index=match.end(),
                        source=source,
                        entity_type=entity_type,
                        entity_name=entity_name,
                        transformation=transformation,
                    ),
                )
        return findings

    def _manual_findings(self, text: str, spans: list[ManualTextSpan]) -> list[FindingRecord]:
        findings: list[FindingRecord] = []
        for span in spans:
            findings.append(
                self._build_text_finding(
                    text=text,
                    start_index=span.start_index,
                    end_index=span.end_index,
                    source=FindingSource.MANUAL,
                    entity_type=span.entity_type,
                    entity_name=span.entity_name or span.entity_type,
                    transformation=span.transformation,
                ),
            )
        return findings

    def _build_text_finding(
        self,
        *,
        text: str,
        start_index: int,
        end_index: int,
        source: FindingSource,
        entity_type: str,
        entity_name: str,
        transformation: TransformationRule | None,
    ) -> FindingRecord:
        matched_text = text[start_index:end_index]
        return FindingRecord(
            source=source,
            kind=FindingKind.TEXT_SPAN,
            entity_type=entity_type,
            entity_name=entity_name,
            start_index=start_index,
            end_index=end_index,
            matched_text_preview=preview_value(matched_text),
            matched_text_hash=hash_value(matched_text),
            transformation=transformation,
        )

    def _deduplicate_findings(self, findings: list[FindingRecord]) -> list[FindingRecord]:
        deduplicated: list[FindingRecord] = []
        seen: set[tuple[object, ...]] = set()
        for finding in sorted(
            findings,
            key=lambda item: (item.start_index or 0, item.end_index or 0, item.entity_type),
        ):
            key = (
                finding.source,
                finding.kind,
                finding.entity_type,
                finding.start_index,
                finding.end_index,
                finding.matched_text_hash,
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(finding)
        return deduplicated

    def _persist_job(
        self,
        *,
        title: str | None,
        content_type: ContentType,
        content: str | None,
        pattern_ids: list[str],
        custom_entity_ids: list[str],
        configuration_ids: list[str],
        findings: list[FindingRecord],
        commit: bool = True,
    ) -> str:
        job = Job(
            title=title,
            status=JobStatus.ANALYZED,
            content_type=content_type,
            source_text=content,
            pattern_ids=pattern_ids,
            custom_entity_ids=custom_entity_ids,
            configuration_ids=configuration_ids,
            summary=summarize_findings(findings),
        )
        self.session.add(job)
        self.session.flush()

        for finding in findings:
            row = JobFinding(
                job_id=job.id,
                source=finding.source,
                kind=finding.kind,
                entity_type=finding.entity_type,
                entity_name=finding.entity_name,
                start_index=finding.start_index,
                end_index=finding.end_index,
                matched_text_preview=finding.matched_text_preview,
                matched_text_hash=finding.matched_text_hash,
                confidence=finding.confidence,
                decision=finding.decision,
                transformation=(
                    finding.transformation.model_dump()
                    if finding.transformation is not None
                    else None
                ),
                extra_data=finding.metadata,
            )
            self.session.add(row)
            self.session.flush()
            finding.id = row.id
            finding.job_id = job.id

        if commit:
            self.session.commit()
        return job.id

    def persist_analyzed_job(
        self,
        *,
        title: str | None,
        content_type: ContentType,
        content: str | None,
        pattern_ids: list[str],
        custom_entity_ids: list[str],
        configuration_ids: list[str],
        findings: list[FindingRecord],
        commit: bool = True,
    ) -> str:
        """Persist a detected text workflow job and its findings."""

        return self._persist_job(
            title=title,
            content_type=content_type,
            content=content,
            pattern_ids=pattern_ids,
            custom_entity_ids=custom_entity_ids,
            configuration_ids=configuration_ids,
            findings=findings,
            commit=commit,
        )
