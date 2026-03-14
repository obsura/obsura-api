"""Text detection workflows for built-in and user-defined rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import HTTPException, status
from pydantic import ValidationError
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
from obsura_api.domain.pii import PIIDetectionOptions, merge_pii_detection_options
from obsura_api.domain.studio import PatternMatcherDefinition
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord, ManualTextSpan, TextAnalysisRequest, TextAnalysisResponse
from obsura_api.services.privacy import sanitize_persisted_finding_metadata
from obsura_api.services.studio import StudioService
from obsura_api.services.utils import hash_value, preview_value, summarize_findings, unique_ids
from obsura_api.services.providers.pii import DetectedPIIEntity, NoOpPIIDetector, PIIDetector


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

    def __init__(
        self,
        session: Session,
        settings: Settings,
        pii_detector: PIIDetector | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.studio = StudioService(session)
        self.pii_detector = pii_detector or NoOpPIIDetector()

    def analyze(self, request: TextAnalysisRequest) -> TextAnalysisResponse:
        self._validate_content_size(request.content)
        (
            patterns,
            entities,
            pattern_ids,
            custom_entity_ids,
            configuration_ids,
            default_transformation,
            pii_detection,
        ) = self.resolve_detection_context(
            content_type=request.content_type,
            pattern_ids=request.pattern_ids,
            custom_entity_ids=request.custom_entity_ids,
            configuration_ids=request.configuration_ids,
            default_transformation=request.default_transformation,
            pii_detection=request.pii_detection,
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
            pii_detection=pii_detection,
        )

        job_id: str | None = None
        if request.persist_job:
            job_id = self.persist_analyzed_job(
                title=request.title,
                content_type=request.content_type,
                content=None,
                pattern_ids=pattern_ids,
                custom_entity_ids=custom_entity_ids,
                configuration_ids=configuration_ids,
                findings=findings,
            )

        summary = summarize_findings(findings)
        return TextAnalysisResponse(job_id=job_id, findings=findings, summary=summary)

    def _validate_content_size(self, content: str) -> None:
        if len(content) <= self.settings.max_bulk_text_item_characters:
            return
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "Text content exceeds the configured maximum of "
                f"{self.settings.max_bulk_text_item_characters} characters"
            ),
        )

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
        pii_detection: PIIDetectionOptions | None = None,
    ) -> list[FindingRecord]:
        """Build transient findings for text content without persisting a job."""

        findings: list[FindingRecord] = []
        if apply_builtins:
            findings.extend(self._detect_built_ins(content, default_transformation))
            findings.extend(
                self._detect_pii_entities(
                    content,
                    default_transformation,
                    pii_detection=pii_detection,
                    existing_findings=findings,
                ),
            )

        for pattern in patterns:
            matcher = PatternMatcherDefinition.model_validate(pattern.matcher)
            if not self._matcher_supports_content_type(matcher.applies_to, content_type):
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
                if not self._matcher_supports_content_type(matcher.applies_to, content_type):
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
        pii_detection: PIIDetectionOptions | None = None,
    ) -> tuple[list[object], list[object], TransformationRule | None, PIIDetectionOptions | None]:
        """Resolve reusable detection inputs for transient text analysis."""

        patterns, entities, _, _, _, resolved_default, resolved_pii_detection = self.resolve_detection_context(
            content_type=content_type,
            pattern_ids=pattern_ids,
            custom_entity_ids=custom_entity_ids,
            configuration_ids=configuration_ids,
            default_transformation=default_transformation,
            pii_detection=pii_detection,
        )
        return patterns, entities, resolved_default, resolved_pii_detection

    def resolve_detection_context(
        self,
        *,
        content_type: ContentType,
        pattern_ids: list[str],
        custom_entity_ids: list[str],
        configuration_ids: list[str],
        default_transformation: TransformationRule | None,
        pii_detection: PIIDetectionOptions | None,
    ) -> tuple[
        list[object],
        list[object],
        list[str],
        list[str],
        list[str],
        TransformationRule | None,
        PIIDetectionOptions | None,
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
        resolved_pii_detection = self._resolve_pii_detection(
            pii_detection,
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
            resolved_pii_detection,
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

    def _matcher_supports_content_type(
        self,
        applies_to: list[ContentType],
        content_type: ContentType,
    ) -> bool:
        if content_type in applies_to:
            return True
        if content_type is ContentType.DOCUMENT:
            return ContentType.TEXT in applies_to
        if content_type is ContentType.CSV:
            return ContentType.STRUCTURED_TEXT in applies_to or ContentType.TEXT in applies_to
        return False

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
                        confidence=1.0,
                    ),
                )
        return findings

    def _detect_pii_entities(
        self,
        text: str,
        default_transformation: TransformationRule | None,
        *,
        pii_detection: PIIDetectionOptions | None,
        existing_findings: list[FindingRecord],
    ) -> list[FindingRecord]:
        if not self.pii_detector.supported:
            return []

        findings: list[FindingRecord] = []
        detector_language = pii_detection.language if pii_detection is not None else None
        detector_entities = pii_detection.entity_allow_list if pii_detection is not None else None
        detector_context = pii_detection.context_words if pii_detection is not None else None
        try:
            detected_entities = self.pii_detector.detect_entities(
                text,
                language=detector_language,
                entity_allow_list=detector_entities,
                context_words=detector_context,
            )
        except TypeError:
            detected_entities = self.pii_detector.detect_entities(text)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        for entity in detected_entities:
            if self._overlaps_existing_span(entity, existing_findings):
                continue
            findings.append(
                self._build_text_finding(
                    text=text,
                    start_index=entity.start_index,
                    end_index=entity.end_index,
                    source=FindingSource.BUILT_IN,
                    entity_type=entity.entity_type,
                    entity_name=self._pii_entity_name(entity),
                    transformation=default_transformation
                    or TransformationRule(
                        mode=TransformationMode.SEMANTIC,
                        semantic_label=entity.entity_type,
                    ),
                    confidence=entity.confidence,
                ),
            )
        return findings

    def _resolve_pii_detection(
        self,
        request_pii_detection: PIIDetectionOptions | None,
        configurations: list[object],
    ) -> PIIDetectionOptions | None:
        configuration_options = [
            self._configuration_pii_detection(configuration)
            for configuration in configurations
        ]
        resolved = merge_pii_detection_options(*configuration_options, request_pii_detection)
        if resolved is None:
            return None

        supported_languages = tuple(getattr(self.pii_detector, "supported_languages", ()) or ())
        if resolved.language and supported_languages and resolved.language not in supported_languages:
            supported = ", ".join(supported_languages)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Unsupported PII language `{resolved.language}` for this deployment. "
                    f"Supported languages: {supported}"
                ),
            )
        return resolved

    def _configuration_pii_detection(self, configuration: object) -> PIIDetectionOptions | None:
        raw_value = getattr(configuration, "extra_data", {}).get("pii_detection")
        if raw_value is None:
            return None
        try:
            return PIIDetectionOptions.model_validate(raw_value)
        except ValidationError as exc:
            configuration_name = getattr(configuration, "name", getattr(configuration, "id", "configuration"))
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Configuration `{configuration_name}` has invalid `pii_detection` settings",
            ) from exc

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
                        confidence=1.0,
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
                        confidence=1.0,
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
                    confidence=1.0,
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
        confidence: float,
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
            confidence=confidence,
            transformation=transformation,
        )

    def _pii_entity_name(self, entity: DetectedPIIEntity) -> str:
        overrides = {
            "EMAIL_ADDRESS": "Email address",
            "IP_ADDRESS": "IP address",
            "URL": "URL",
            "PHONE_NUMBER": "Phone number",
            "PERSON": "Person name",
            "LOCATION": "Location",
            "DATE_TIME": "Date/time",
            "CREDIT_CARD": "Credit card number",
            "US_SSN": "US social security number",
            "IBAN_CODE": "IBAN code",
        }
        if entity.entity_type in overrides:
            return overrides[entity.entity_type]
        return entity.entity_type.replace("_", " ").title()

    def _overlaps_existing_span(
        self,
        entity: DetectedPIIEntity,
        findings: list[FindingRecord],
    ) -> bool:
        for finding in findings:
            if finding.start_index is None or finding.end_index is None:
                continue
            if entity.start_index < finding.end_index and entity.end_index > finding.start_index:
                return True
        return False

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
                matched_text_preview=None,
                matched_text_hash=finding.matched_text_hash,
                confidence=finding.confidence,
                decision=finding.decision,
                transformation=(
                    finding.transformation.model_dump()
                    if finding.transformation is not None
                    else None
                ),
                extra_data=sanitize_persisted_finding_metadata(finding.metadata),
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
