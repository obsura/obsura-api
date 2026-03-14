"""Text transformation workflows built on reviewable findings."""

from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from obsura_api.db.models import Job, JobOutput
from obsura_api.domain.enums import ContentType, FindingSource, JobStatus, ReviewDecision, TransformationMode
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import (
    FindingOverride,
    FindingRecord,
    ReplacementRecord,
    TextTransformRequest,
    TextTransformResponse,
)
from obsura_api.services.jobs import finding_to_schema
from obsura_api.services.utils import hash_value, normalize_token, summarize_findings


SOURCE_PRIORITY = {
    FindingSource.MANUAL: 0,
    FindingSource.CUSTOM: 1,
    FindingSource.FACE: 1,
    FindingSource.OCR: 2,
    FindingSource.BUILT_IN: 3,
}


class TextTransformationService:
    """Apply approved or pending findings to text content."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def transform_job(self, request: TextTransformRequest) -> TextTransformResponse:
        if not request.job_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="`job_id` is required for direct transform requests",
            )

        job = self._load_text_job(str(request.job_id))
        return self.transform_loaded_job(job, request)

    def persist_text_output(
        self,
        *,
        job_id: str,
        output_text: str,
        replacement_count: int,
    ) -> None:
        """Persist a text output for an existing job."""

        job = self.session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.TRANSFORMED
        output = JobOutput(
            job_id=job.id,
            content_type=job.content_type,
            output_text=None,
            extra_data={
                "replacement_count": replacement_count,
                "output_hash": hash_value(output_text),
            },
        )
        self.session.add(output)
        self.session.commit()

    def transform_loaded_job(
        self,
        job: Job,
        request: TextTransformRequest,
        *,
        commit: bool = True,
    ) -> TextTransformResponse:
        """Transform a loaded text job."""

        if job.content_type not in {ContentType.TEXT, ContentType.STRUCTURED_TEXT}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Only text jobs can be transformed with this endpoint",
            )

        stored_findings = {item.id: item for item in job.findings}
        for override in request.finding_overrides:
            self._apply_override(stored_findings, override)

        content = request.content or job.source_text
        if not content:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Job does not retain source text; resubmit content to transform it",
            )

        findings = [finding_to_schema(item) for item in job.findings]
        output_text, replacements = self.apply_findings(
            content=content,
            findings=findings,
            include_pending=request.include_pending,
            default_transformation=request.default_transformation,
        )

        if request.persist_output:
            job.status = JobStatus.TRANSFORMED
            job.summary = summarize_findings(findings)
            output = JobOutput(
                job_id=job.id,
                content_type=job.content_type,
                output_text=None,
                extra_data={
                    "replacement_count": len(replacements),
                    "output_hash": hash_value(output_text),
                },
            )
            self.session.add(output)
            if commit:
                self.session.commit()

        return TextTransformResponse(
            job_id=job.id,
            output_text=output_text,
            replacements=replacements,
            summary={"replacement_count": len(replacements)},
        )

    def apply_findings(
        self,
        *,
        content: str,
        findings: list[FindingRecord],
        include_pending: bool,
        default_transformation: TransformationRule | None,
    ) -> tuple[str, list[ReplacementRecord]]:
        active = [
            item
            for item in findings
            if item.start_index is not None
            and item.end_index is not None
            and (
                item.decision is ReviewDecision.APPROVED
                or (include_pending and item.decision is ReviewDecision.PENDING)
            )
        ]
        selected = self._select_non_overlapping(active)

        cursor = 0
        output_parts: list[str] = []
        replacements: list[ReplacementRecord] = []
        alias_counts: dict[str, int] = defaultdict(int)
        alias_map: dict[str, str] = {}

        for finding in selected:
            start_index = finding.start_index or 0
            end_index = finding.end_index or 0
            output_parts.append(content[cursor:start_index])
            original_value = content[start_index:end_index]
            rule = finding.transformation or default_transformation or TransformationRule()
            replacement_value = self._render_replacement(
                original_value=original_value,
                finding=finding,
                rule=rule,
                alias_map=alias_map,
                alias_counts=alias_counts,
            )
            output_parts.append(replacement_value)
            replacements.append(
                ReplacementRecord(
                    entity_type=finding.entity_type,
                    start_index=start_index,
                    end_index=end_index,
                    original_preview=finding.matched_text_preview,
                    output_value=replacement_value,
                ),
            )
            cursor = end_index

        output_parts.append(content[cursor:])
        return "".join(output_parts), replacements

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

    def _select_non_overlapping(self, findings: list[FindingRecord]) -> list[FindingRecord]:
        selected: list[FindingRecord] = []
        for finding in sorted(
            findings,
            key=lambda item: (
                SOURCE_PRIORITY.get(item.source, 99),
                -((item.end_index or 0) - (item.start_index or 0)),
                item.start_index or 0,
            ),
        ):
            if self._overlaps_any(selected, finding):
                continue
            selected.append(finding)
        return sorted(selected, key=lambda item: item.start_index or 0)

    def _overlaps_any(self, selected: list[FindingRecord], candidate: FindingRecord) -> bool:
        candidate_start = candidate.start_index or 0
        candidate_end = candidate.end_index or 0
        for existing in selected:
            existing_start = existing.start_index or 0
            existing_end = existing.end_index or 0
            if candidate_start < existing_end and existing_start < candidate_end:
                return True
        return False

    def _render_replacement(
        self,
        *,
        original_value: str,
        finding: FindingRecord,
        rule: TransformationRule,
        alias_map: dict[str, str],
        alias_counts: dict[str, int],
    ) -> str:
        if rule.mode is TransformationMode.SEMANTIC:
            return f"[{normalize_token(rule.semantic_label or finding.entity_type)}]"

        if rule.mode in {TransformationMode.GENERIC, TransformationMode.CUSTOM}:
            return rule.placeholder or "[REDACTED]"

        if rule.mode is TransformationMode.MASK:
            return rule.mask_character * max(len(original_value), 1)

        if rule.mode is TransformationMode.PARTIAL_MASK:
            visible_prefix = rule.prefix_visible
            visible_suffix = rule.suffix_visible
            if visible_prefix + visible_suffix >= len(original_value):
                return original_value
            masked = rule.mask_character * max(
                len(original_value) - visible_prefix - visible_suffix,
                1,
            )
            suffix = (
                original_value[len(original_value) - visible_suffix:]
                if visible_suffix
                else ""
            )
            return f"{original_value[:visible_prefix]}{masked}{suffix}"

        if rule.mode is TransformationMode.STABLE_ALIAS:
            key = finding.matched_text_hash or original_value
            if key not in alias_map:
                prefix = normalize_token(rule.alias_prefix or finding.entity_type)
                alias_counts[prefix] += 1
                alias_map[key] = f"{prefix}_{alias_counts[prefix]}"
            return alias_map[key]

        return rule.placeholder or f"[{normalize_token(finding.entity_type)}]"

    def _load_text_job(self, job_id: str) -> Job:
        job = self.session.scalar(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.findings), selectinload(Job.outputs)),
        )
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job
