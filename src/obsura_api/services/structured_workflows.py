"""Structured JSON analysis and transformation workflows."""

from __future__ import annotations

import copy
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobOutput
from obsura_api.domain.enums import ContentType, FindingKind, JobStatus
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.structured import (
    StructuredAnalysisRequest,
    StructuredJobTransformRequest,
    StructuredReplacementRecord,
    StructuredTransformRequest,
    StructuredWorkflowResponse,
)
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride, FindingRecord
from obsura_api.services.detection import TextDetectionService
from obsura_api.services.jobs import finding_to_schema
from obsura_api.services.providers.pii import NoOpPIIDetector, PIIDetector
from obsura_api.services.providers.text_anonymizer import NativeTextAnonymizer, TextAnonymizer
from obsura_api.services.text_transformations import TextTransformationService
from obsura_api.services.utils import hash_value, summarize_findings


@dataclass(slots=True)
class StructuredPayloadStats:
    """Running counters used to enforce structured payload limits."""

    node_count: int = 0
    total_characters: int = 0


class StructuredWorkflowService:
    """Analyze and transform structured JSON content using leaf-string detection."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        pii_detector: PIIDetector | None = None,
        text_anonymizer: TextAnonymizer | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.text_detection = TextDetectionService(
            session,
            settings,
            pii_detector=pii_detector or NoOpPIIDetector(),
        )
        self.text_transformations = TextTransformationService(
            session,
            settings,
            text_anonymizer=text_anonymizer
            or NativeTextAnonymizer(hash_salt=settings.text_hash_salt),
        )

    def analyze(self, request: StructuredAnalysisRequest) -> StructuredWorkflowResponse:
        self._validate_payload_limits(request.data)
        (
            patterns,
            entities,
            pattern_ids,
            custom_entity_ids,
            configuration_ids,
            default_transformation,
            pii_detection,
        ) = self.text_detection.resolve_detection_context(
            content_type=ContentType.STRUCTURED_TEXT,
            pattern_ids=request.pattern_ids,
            custom_entity_ids=request.custom_entity_ids,
            configuration_ids=request.configuration_ids,
            default_transformation=request.default_transformation,
            pii_detection=request.pii_detection,
        )
        findings = self._build_findings(
            data=request.data,
            apply_builtins=request.apply_builtins,
            exact_values=request.exact_values,
            patterns=patterns,
            entities=entities,
            default_transformation=default_transformation,
            pii_detection=pii_detection,
        )
        job_id = None
        if request.persist_job:
            job_id = self.text_detection.persist_analyzed_job(
                title=request.title,
                content_type=ContentType.STRUCTURED_TEXT,
                content=None,
                pattern_ids=pattern_ids,
                custom_entity_ids=custom_entity_ids,
                configuration_ids=configuration_ids,
                findings=findings,
            )
        return StructuredWorkflowResponse(
            job_id=job_id,
            findings=findings,
            summary=summarize_findings(findings),
        )

    def transform(self, request: StructuredTransformRequest) -> StructuredWorkflowResponse:
        self._validate_payload_limits(request.data)
        analysis = self.analyze(
            StructuredAnalysisRequest(
                title=request.title,
                data=request.data,
                apply_builtins=request.apply_builtins,
                pattern_ids=request.pattern_ids,
                custom_entity_ids=request.custom_entity_ids,
                configuration_ids=request.configuration_ids,
                pii_detection=request.pii_detection,
                exact_values=request.exact_values,
                default_transformation=request.default_transformation,
                persist_job=request.persist_job,
                persist_source_content=request.persist_source_content,
            ),
        )
        output_data, replacements = self._apply_structured_findings(
            data=request.data,
            findings=analysis.findings,
            include_pending=True,
            default_transformation=request.default_transformation,
        )
        if analysis.job_id and request.persist_output:
            self._persist_structured_output(
                job_id=analysis.job_id,
                output_data=output_data,
                replacement_count=len(replacements),
            )
        return StructuredWorkflowResponse(
            job_id=analysis.job_id,
            findings=analysis.findings,
            output_data=output_data,
            replacements=replacements,
            summary=self._transform_summary(replacements),
        )

    def transform_job(self, request: StructuredJobTransformRequest) -> StructuredWorkflowResponse:
        self._validate_payload_limits(request.data)
        job = self.session.get(Job, request.job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.content_type is not ContentType.STRUCTURED_TEXT:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Only structured text jobs can be transformed with this endpoint",
            )

        stored_findings = {item.id: item for item in job.findings}
        for override in request.finding_overrides:
            self._apply_override(stored_findings, override)

        findings = [finding_to_schema(item) for item in job.findings]
        output_data, replacements = self._apply_structured_findings(
            data=request.data,
            findings=findings,
            include_pending=request.include_pending,
            default_transformation=request.default_transformation,
        )
        if request.persist_output:
            self._persist_structured_output(
                job_id=job.id,
                output_data=output_data,
                replacement_count=len(replacements),
            )
        return StructuredWorkflowResponse(
            job_id=job.id,
            findings=findings,
            output_data=output_data,
            replacements=replacements,
            summary=self._transform_summary(replacements),
        )

    def _build_findings(
        self,
        *,
        data: dict[str, Any] | list[Any],
        apply_builtins: bool,
        exact_values: list[str],
        patterns: list[object],
        entities: list[object],
        default_transformation: TransformationRule | None,
        pii_detection: PIIDetectionOptions | None,
    ) -> list[FindingRecord]:
        findings: list[FindingRecord] = []
        for path_tokens, path, value in self._iter_string_leaves(data):
            text_findings = self.text_detection.build_findings(
                content=value,
                content_type=ContentType.STRUCTURED_TEXT,
                apply_builtins=apply_builtins,
                exact_values=exact_values,
                manual_spans=[],
                patterns=patterns,
                entities=entities,
                default_transformation=default_transformation,
                pii_detection=pii_detection,
            )
            for finding in text_findings:
                metadata = dict(finding.metadata)
                metadata.update(
                    {
                        "structured_path": path,
                        "structured_path_tokens": self._serialize_path_tokens(path_tokens),
                        "structured_value_kind": "string",
                    },
                )
                findings.append(
                    finding.model_copy(
                        update={
                            "kind": FindingKind.STRUCTURED_FIELD,
                            "metadata": metadata,
                        },
                    ),
                )
        return findings

    def _apply_structured_findings(
        self,
        *,
        data: dict[str, Any] | list[Any],
        findings: list[FindingRecord],
        include_pending: bool,
        default_transformation: TransformationRule | None,
    ) -> tuple[dict[str, Any] | list[Any], list[StructuredReplacementRecord]]:
        transformed_data = copy.deepcopy(data)
        findings_by_path: dict[tuple[str, ...], list[FindingRecord]] = defaultdict(list)
        path_labels: dict[tuple[str, ...], str] = {}

        for finding in findings:
            path_tokens = self._structured_path_tokens(finding)
            path = self._structured_path(finding)
            findings_by_path[path_tokens].append(finding)
            path_labels[path_tokens] = path

        replacements: list[StructuredReplacementRecord] = []
        for path_tokens, leaf_findings in findings_by_path.items():
            value = self._resolve_leaf_value(transformed_data, path_tokens, path_labels[path_tokens])
            output_text, leaf_replacements = self.text_transformations.apply_findings(
                content=value,
                findings=leaf_findings,
                include_pending=include_pending,
                default_transformation=default_transformation,
            )
            self._set_leaf_value(transformed_data, path_tokens, output_text, path_labels[path_tokens])
            for replacement in leaf_replacements:
                replacements.append(
                    StructuredReplacementRecord(
                        entity_type=replacement.entity_type,
                        path=path_labels[path_tokens],
                        start_index=replacement.start_index,
                        end_index=replacement.end_index,
                        original_preview=replacement.original_preview,
                        output_value=replacement.output_value,
                    ),
                )
        return transformed_data, replacements

    def _validate_payload_limits(self, data: dict[str, Any] | list[Any]) -> None:
        stats = StructuredPayloadStats()
        self._walk_payload(data, depth=1, stats=stats)

    def _walk_payload(
        self,
        value: Any,
        *,
        depth: int,
        stats: StructuredPayloadStats,
    ) -> None:
        if depth > self.settings.max_structured_payload_depth:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Structured payload exceeds the configured maximum depth of "
                    f"{self.settings.max_structured_payload_depth}"
                ),
            )
        stats.node_count += 1
        if stats.node_count > self.settings.max_structured_payload_nodes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Structured payload exceeds the configured maximum node count of "
                    f"{self.settings.max_structured_payload_nodes}"
                ),
            )

        if value is None or isinstance(value, (bool, int)):
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Structured JSON values must not contain NaN or Infinity",
                )
            return
        if isinstance(value, str):
            stats.total_characters += len(value)
            self._assert_character_limit(stats)
            return
        if isinstance(value, list):
            for item in value:
                self._walk_payload(item, depth=depth + 1, stats=stats)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                stats.total_characters += len(key)
                self._assert_character_limit(stats)
                self._walk_payload(item, depth=depth + 1, stats=stats)
            return
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Structured workflows only support JSON-compatible objects and arrays",
        )

    def _assert_character_limit(self, stats: StructuredPayloadStats) -> None:
        if stats.total_characters <= self.settings.max_structured_payload_characters:
            return
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "Structured payload exceeds the configured total character limit of "
                f"{self.settings.max_structured_payload_characters}"
            ),
        )

    def _iter_string_leaves(
        self,
        value: dict[str, Any] | list[Any] | str,
        path_tokens: tuple[str | int, ...] = (),
    ) -> list[tuple[tuple[str | int, ...], str, str]]:
        leaves: list[tuple[tuple[str | int, ...], str, str]] = []
        if isinstance(value, str):
            if value:
                leaves.append((path_tokens, self._format_path(path_tokens), value))
            return leaves
        if isinstance(value, list):
            for index, item in enumerate(value):
                leaves.extend(self._iter_string_leaves(item, path_tokens + (index,)))
            return leaves
        for key, item in value.items():
            leaves.extend(self._iter_string_leaves(item, path_tokens + (key,)))
        return leaves

    def _format_path(self, path_tokens: tuple[str | int, ...]) -> str:
        parts = ["$"]
        for token in path_tokens:
            if isinstance(token, int):
                parts.append(f"[{token}]")
            elif token.isidentifier():
                parts.append(f".{token}")
            else:
                parts.append(f"[{json.dumps(token)}]")
        return "".join(parts)

    def _serialize_path_tokens(self, path_tokens: tuple[str | int, ...]) -> list[str]:
        serialized: list[str] = []
        for token in path_tokens:
            if isinstance(token, int):
                serialized.append(f"i:{token}")
            else:
                serialized.append(f"s:{token}")
        return serialized

    def _deserialize_path_tokens(self, raw_tokens: list[str]) -> tuple[str | int, ...]:
        tokens: list[str | int] = []
        for item in raw_tokens:
            if item.startswith("i:"):
                try:
                    tokens.append(int(item[2:]))
                except ValueError as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Stored structured path metadata is invalid",
                    ) from exc
            elif item.startswith("s:"):
                tokens.append(item[2:])
            else:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Stored structured path metadata is invalid",
                )
        return tuple(tokens)

    def _structured_path_tokens(self, finding: FindingRecord) -> tuple[str | int, ...]:
        raw_tokens = finding.metadata.get("structured_path_tokens")
        if not isinstance(raw_tokens, list) or not all(isinstance(item, str) for item in raw_tokens):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Structured finding is missing safe path metadata",
            )
        return self._deserialize_path_tokens(raw_tokens)

    def _structured_path(self, finding: FindingRecord) -> str:
        path = finding.metadata.get("structured_path")
        if not isinstance(path, str) or not path:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Structured finding is missing safe path metadata",
            )
        return path

    def _resolve_leaf_value(
        self,
        data: dict[str, Any] | list[Any],
        path_tokens: tuple[str | int, ...],
        path: str,
    ) -> str:
        current: Any = data
        for token in path_tokens:
            try:
                current = current[token]
            except (KeyError, IndexError, TypeError) as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Structured payload no longer matches stored finding path `{path}`",
                ) from exc
        if not isinstance(current, str):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Structured payload path `{path}` must resolve to a string value",
            )
        return current

    def _set_leaf_value(
        self,
        data: dict[str, Any] | list[Any],
        path_tokens: tuple[str | int, ...],
        value: str,
        path: str,
    ) -> None:
        if not path_tokens:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Structured payload path `{path}` is invalid",
            )
        parent: Any = data
        for token in path_tokens[:-1]:
            try:
                parent = parent[token]
            except (KeyError, IndexError, TypeError) as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Structured payload no longer matches stored finding path `{path}`",
                ) from exc
        leaf_token = path_tokens[-1]
        try:
            parent[leaf_token] = value
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Structured payload no longer matches stored finding path `{path}`",
            ) from exc

    def _apply_override(
        self,
        stored_findings: dict[str, object],
        override: FindingOverride,
    ) -> None:
        if not override.finding_id:
            return
        finding = stored_findings.get(override.finding_id)
        if finding is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Finding {override.finding_id} not found",
            )
        if override.decision is not None:
            finding.decision = override.decision
        if override.transformation is not None:
            finding.transformation = override.transformation.model_dump()

    def _persist_structured_output(
        self,
        *,
        job_id: str,
        output_data: dict[str, Any] | list[Any],
        replacement_count: int,
    ) -> None:
        job = self.session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.TRANSFORMED
        output_json = json.dumps(output_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        output = JobOutput(
            job_id=job.id,
            content_type=job.content_type,
            output_text=None,
            extra_data={
                "replacement_count": replacement_count,
                "output_hash": hash_value(output_json),
                "structured_root_type": "array" if isinstance(output_data, list) else "object",
            },
        )
        self.session.add(output)
        self.session.commit()

    def _transform_summary(self, replacements: list[StructuredReplacementRecord]) -> dict[str, int]:
        return {
            "replacement_count": len(replacements),
            "transformed_path_count": len({item.path for item in replacements}),
        }
