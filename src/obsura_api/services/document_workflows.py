"""PDF document analysis and transformation workflows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobOutput
from obsura_api.domain.documents import (
    DocumentJobTransformRequest,
    DocumentPageResult,
    DocumentReplacementRecord,
    DocumentWorkflowManifest,
    DocumentWorkflowResponse,
)
from obsura_api.domain.enums import ContentType, JobStatus
from obsura_api.domain.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnprocessableContentError,
)
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride, FindingRecord
from obsura_api.services.detection import TextDetectionService
from obsura_api.services.jobs import finding_to_schema
from obsura_api.services.providers.documents import (
    DocumentExtractor,
    ExtractedDocument,
    ExtractedDocumentPage,
    NoOpDocumentExtractor,
)
from obsura_api.services.providers.pii import NoOpPIIDetector, PIIDetector
from obsura_api.services.providers.text_anonymizer import NativeTextAnonymizer, TextAnonymizer
from obsura_api.services.text_transformations import TextTransformationService
from obsura_api.services.utils import hash_value, summarize_findings


@dataclass(slots=True)
class ResolvedDocumentAnalysis:
    """Resolved transient analysis inputs for one extracted PDF."""

    title: str | None
    document: ExtractedDocument
    findings: list[FindingRecord]
    pattern_ids: list[str]
    custom_entity_ids: list[str]
    configuration_ids: list[str]
    default_transformation: TransformationRule | None


class DocumentWorkflowService:
    """Analyze and transform PDF document text without persisting raw files."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        document_extractor: DocumentExtractor | None = None,
        pii_detector: PIIDetector | None = None,
        text_anonymizer: TextAnonymizer | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.document_extractor = document_extractor or NoOpDocumentExtractor()
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

    def analyze(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: DocumentWorkflowManifest,
    ) -> DocumentWorkflowResponse:
        resolved = self._resolve_analysis(
            file_bytes=file_bytes,
            filename=filename,
            manifest=manifest,
        )
        job_id = None
        if manifest.persist_job:
            job_id = self.text_detection.persist_analyzed_job(
                title=resolved.title,
                content_type=ContentType.DOCUMENT,
                content=None,
                pattern_ids=resolved.pattern_ids,
                custom_entity_ids=resolved.custom_entity_ids,
                configuration_ids=resolved.configuration_ids,
                findings=resolved.findings,
            )
        return DocumentWorkflowResponse(
            job_id=job_id,
            findings=resolved.findings,
            page_count=resolved.document.page_count,
            extracted_character_count=resolved.document.extracted_character_count,
            pages=self._page_results(resolved.document.pages),
            summary=summarize_findings(resolved.findings),
        )

    def transform(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: DocumentWorkflowManifest,
    ) -> DocumentWorkflowResponse:
        resolved = self._resolve_analysis(
            file_bytes=file_bytes,
            filename=filename,
            manifest=manifest,
        )
        job_id = None
        if manifest.persist_job:
            job_id = self.text_detection.persist_analyzed_job(
                title=resolved.title,
                content_type=ContentType.DOCUMENT,
                content=None,
                pattern_ids=resolved.pattern_ids,
                custom_entity_ids=resolved.custom_entity_ids,
                configuration_ids=resolved.configuration_ids,
                findings=resolved.findings,
            )

        pages, output_text, replacements = self._apply_document_findings(
            pages=resolved.document.pages,
            findings=resolved.findings,
            include_pending=True,
            default_transformation=resolved.default_transformation,
            validate_page_hash=False,
        )
        if job_id is not None:
            self._persist_document_output(
                job_id=job_id,
                output_text=output_text,
                page_count=len(pages),
                replacement_count=len(replacements),
            )
        return DocumentWorkflowResponse(
            job_id=job_id,
            findings=resolved.findings,
            page_count=len(pages),
            extracted_character_count=sum(item.character_count for item in pages),
            pages=pages,
            output_text=output_text,
            replacements=replacements,
            summary=self._transform_summary(replacements),
        )

    def transform_job(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        request: DocumentJobTransformRequest,
    ) -> DocumentWorkflowResponse:
        _ = filename
        document = self._extract_document(file_bytes)
        job = self.session.get(Job, request.job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if job.content_type is not ContentType.DOCUMENT:
            raise BadRequestError("Only document jobs can be transformed with this endpoint")

        stored_findings = {item.id: item for item in job.findings}
        for override in request.finding_overrides:
            self._apply_override(stored_findings, override)

        findings = [finding_to_schema(item) for item in job.findings]
        pages, output_text, replacements = self._apply_document_findings(
            pages=document.pages,
            findings=findings,
            include_pending=request.include_pending,
            default_transformation=request.default_transformation,
            validate_page_hash=True,
        )
        if request.persist_output:
            self._persist_document_output(
                job_id=job.id,
                output_text=output_text,
                page_count=len(pages),
                replacement_count=len(replacements),
            )
        return DocumentWorkflowResponse(
            job_id=job.id,
            findings=findings,
            page_count=len(pages),
            extracted_character_count=sum(item.character_count for item in pages),
            pages=pages,
            output_text=output_text,
            replacements=replacements,
            summary=self._transform_summary(replacements),
        )

    def _resolve_analysis(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: DocumentWorkflowManifest,
    ) -> ResolvedDocumentAnalysis:
        document = self._extract_document(file_bytes)
        (
            patterns,
            entities,
            pattern_ids,
            custom_entity_ids,
            configuration_ids,
            default_transformation,
            pii_detection,
        ) = self.text_detection.resolve_detection_context(
            content_type=ContentType.DOCUMENT,
            pattern_ids=manifest.pattern_ids,
            custom_entity_ids=manifest.custom_entity_ids,
            configuration_ids=manifest.configuration_ids,
            default_transformation=manifest.default_transformation,
            pii_detection=manifest.pii_detection,
        )
        findings = self._build_findings(
            document=document,
            apply_builtins=manifest.apply_builtins,
            exact_values=manifest.exact_values,
            patterns=patterns,
            entities=entities,
            default_transformation=default_transformation,
            pii_detection=pii_detection,
        )
        return ResolvedDocumentAnalysis(
            title=manifest.title or Path(filename).name,
            document=document,
            findings=findings,
            pattern_ids=pattern_ids,
            custom_entity_ids=custom_entity_ids,
            configuration_ids=configuration_ids,
            default_transformation=default_transformation,
        )

    def _build_findings(
        self,
        *,
        document: ExtractedDocument,
        apply_builtins: bool,
        exact_values: list[str],
        patterns: list[object],
        entities: list[object],
        default_transformation: TransformationRule | None,
        pii_detection: PIIDetectionOptions | None,
    ) -> list[FindingRecord]:
        findings: list[FindingRecord] = []
        for page in document.pages:
            page_findings = self.text_detection.build_findings(
                content=page.text,
                content_type=ContentType.DOCUMENT,
                apply_builtins=apply_builtins,
                exact_values=exact_values,
                manual_spans=[],
                patterns=patterns,
                entities=entities,
                default_transformation=default_transformation,
                pii_detection=pii_detection,
            )
            page_hash = hash_value(page.text)
            for finding in page_findings:
                metadata = dict(finding.metadata)
                metadata.update(
                    {
                        "document_kind": "pdf",
                        "document_page_number": page.page_number,
                        "document_page_label": f"Page {page.page_number}",
                        "document_page_text_hash": page_hash,
                        "document_page_character_count": len(page.text),
                    },
                )
                findings.append(finding.model_copy(update={"metadata": metadata}))
        return findings

    def _apply_document_findings(
        self,
        *,
        pages: list[ExtractedDocumentPage],
        findings: list[FindingRecord],
        include_pending: bool,
        default_transformation: TransformationRule | None,
        validate_page_hash: bool,
    ) -> tuple[list[DocumentPageResult], str, list[DocumentReplacementRecord]]:
        findings_by_page: dict[int, list[FindingRecord]] = defaultdict(list)
        page_hashes: dict[int, str] = {}
        for finding in findings:
            page_number = self._document_page_number(finding)
            findings_by_page[page_number].append(finding)
            page_hash = self._document_page_hash(finding)
            existing_hash = page_hashes.get(page_number)
            if existing_hash is not None and existing_hash != page_hash:
                raise UnprocessableContentError(
                    "Stored document finding metadata is internally inconsistent",
                )
            page_hashes[page_number] = page_hash

        page_lookup = {page.page_number: page for page in pages}
        page_results: list[DocumentPageResult] = []
        replacements: list[DocumentReplacementRecord] = []

        for page in pages:
            page_findings = findings_by_page.get(page.page_number, [])
            if validate_page_hash and page_findings:
                expected_hash = page_hashes[page.page_number]
                actual_hash = hash_value(page.text)
                if actual_hash != expected_hash:
                    raise UnprocessableContentError(
                        "Resubmitted PDF page content does not match the reviewed job for "
                        f"page {page.page_number}",
                    )

            output_text, page_replacements = self.text_transformations.apply_findings(
                content=page.text,
                findings=page_findings,
                include_pending=include_pending,
                default_transformation=default_transformation,
            )
            page_results.append(
                DocumentPageResult(
                    page_number=page.page_number,
                    character_count=len(output_text),
                    output_text=output_text,
                    replacement_count=len(page_replacements),
                ),
            )
            for replacement in page_replacements:
                replacements.append(
                    DocumentReplacementRecord(
                        entity_type=replacement.entity_type,
                        page_number=page.page_number,
                        start_index=replacement.start_index,
                        end_index=replacement.end_index,
                        original_preview=replacement.original_preview,
                        output_value=replacement.output_value,
                    ),
                )

        missing_pages = sorted(set(findings_by_page) - set(page_lookup))
        if missing_pages:
            missing = ", ".join(str(page_number) for page_number in missing_pages)
            raise UnprocessableContentError(
                f"Resubmitted PDF is missing reviewed pages: {missing}",
            )

        return page_results, self._combine_page_output(page_results), replacements

    def _combine_page_output(self, pages: list[DocumentPageResult]) -> str:
        return "\n\n\f\n\n".join(page.output_text or "" for page in pages)

    def _page_results(self, pages: list[ExtractedDocumentPage]) -> list[DocumentPageResult]:
        return [
            DocumentPageResult(
                page_number=page.page_number,
                character_count=len(page.text),
            )
            for page in pages
        ]

    def _extract_document(self, file_bytes: bytes) -> ExtractedDocument:
        if not self.document_extractor.supported:
            raise ConflictError("PDF document workflows are not configured for this deployment")
        return self.document_extractor.extract_pdf(file_bytes)

    def _document_page_number(self, finding: FindingRecord) -> int:
        page_number = finding.metadata.get("document_page_number")
        if not isinstance(page_number, int) or page_number < 1:
            raise UnprocessableContentError("Document finding is missing safe page metadata")
        return page_number

    def _document_page_hash(self, finding: FindingRecord) -> str:
        page_hash = finding.metadata.get("document_page_text_hash")
        if not isinstance(page_hash, str) or not page_hash:
            raise UnprocessableContentError("Document finding is missing safe page hash metadata")
        return page_hash

    def _apply_override(
        self,
        stored_findings: dict[str, object],
        override: FindingOverride,
    ) -> None:
        if not override.finding_id:
            return
        finding = stored_findings.get(override.finding_id)
        if finding is None:
            raise NotFoundError(f"Finding {override.finding_id} not found")
        if override.decision is not None:
            finding.decision = override.decision
        if override.transformation is not None:
            finding.transformation = override.transformation.model_dump()

    def _persist_document_output(
        self,
        *,
        job_id: str,
        output_text: str,
        page_count: int,
        replacement_count: int,
    ) -> None:
        job = self.session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.TRANSFORMED
        output = JobOutput(
            job_id=job.id,
            content_type=job.content_type,
            output_text=None,
            extra_data={
                "document_kind": "pdf",
                "output_hash": hash_value(output_text),
                "page_count": page_count,
                "replacement_count": replacement_count,
            },
        )
        self.session.add(output)
        self.session.commit()

    def _transform_summary(self, replacements: list[DocumentReplacementRecord]) -> dict[str, int]:
        return {
            "replacement_count": len(replacements),
            "transformed_page_count": len({item.page_number for item in replacements}),
        }
