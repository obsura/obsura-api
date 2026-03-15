"""CSV analysis and transformation workflows."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobFinding, JobOutput
from obsura_api.domain.csv_workflows import (
    CSVJobTransformRequest,
    CSVReplacementRecord,
    CSVWorkflowManifest,
    CSVWorkflowResponse,
)
from obsura_api.domain.enums import ContentType, FindingKind, JobStatus
from obsura_api.domain.errors import (
    BadRequestError,
    NotFoundError,
    PayloadTooLargeError,
    UnprocessableContentError,
    UnsupportedMediaTypeError,
)
from obsura_api.domain.pii import PIIDetectionOptions
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingOverride, FindingRecord
from obsura_api.services.detection import TextDetectionService
from obsura_api.services.jobs import finding_to_schema
from obsura_api.services.providers.pii import NoOpPIIDetector, PIIDetector
from obsura_api.services.providers.text_anonymizer import NativeTextAnonymizer, TextAnonymizer
from obsura_api.services.sharing import build_text_share_policy, share_metadata
from obsura_api.services.text_transformations import TextTransformationService
from obsura_api.services.utils import hash_value, summarize_findings

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(slots=True)
class ParsedCSV:
    """Transient parsed CSV payload."""

    has_header: bool
    headers: list[str]
    rows: list[list[str]]
    physical_row_numbers: list[int]
    column_count: int


@dataclass(slots=True)
class ResolvedCSVAnalysis:
    """Resolved analysis inputs for one CSV file."""

    title: str | None
    parsed: ParsedCSV
    findings: list[FindingRecord]
    pattern_ids: list[str]
    custom_entity_ids: list[str]
    configuration_ids: list[str]
    default_transformation: TransformationRule | None


class CSVWorkflowService:
    """Analyze and transform CSV files without persisting raw file contents."""

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

    def analyze(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: CSVWorkflowManifest,
    ) -> CSVWorkflowResponse:
        resolved = self._resolve_analysis(
            file_bytes=file_bytes,
            filename=filename,
            manifest=manifest,
        )
        job_id = None
        if manifest.persist_job:
            job_id = self.text_detection.persist_analyzed_job(
                title=resolved.title,
                content_type=ContentType.CSV,
                content=None,
                pattern_ids=resolved.pattern_ids,
                custom_entity_ids=resolved.custom_entity_ids,
                configuration_ids=resolved.configuration_ids,
                findings=resolved.findings,
            )
        return CSVWorkflowResponse(
            job_id=job_id,
            findings=resolved.findings,
            has_header=resolved.parsed.has_header,
            headers=resolved.parsed.headers,
            row_count=len(resolved.parsed.rows),
            column_count=resolved.parsed.column_count,
            summary=summarize_findings(resolved.findings),
        )

    def transform(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: CSVWorkflowManifest,
    ) -> CSVWorkflowResponse:
        resolved = self._resolve_analysis(
            file_bytes=file_bytes,
            filename=filename,
            manifest=manifest,
        )
        job_id = None
        if manifest.persist_job:
            job_id = self.text_detection.persist_analyzed_job(
                title=resolved.title,
                content_type=ContentType.CSV,
                content=None,
                pattern_ids=resolved.pattern_ids,
                custom_entity_ids=resolved.custom_entity_ids,
                configuration_ids=resolved.configuration_ids,
                findings=resolved.findings,
            )

        output_rows, output_csv, replacements, formula_escape_count = self._apply_csv_findings(
            parsed=resolved.parsed,
            findings=resolved.findings,
            include_pending=True,
            default_transformation=resolved.default_transformation,
            delimiter=manifest.delimiter,
            quotechar=manifest.quotechar,
            validate_cell_hash=False,
        )
        share_policy = build_text_share_policy(manifest.output_intent)
        if job_id is not None:
            self._persist_csv_output(
                job_id=job_id,
                output_csv=output_csv,
                row_count=len(output_rows),
                column_count=resolved.parsed.column_count,
                replacement_count=len(replacements),
                formula_escape_count=formula_escape_count,
                has_header=resolved.parsed.has_header,
                output_intent=manifest.output_intent,
                share_policy=share_policy,
            )

        return CSVWorkflowResponse(
            job_id=job_id,
            findings=resolved.findings,
            has_header=resolved.parsed.has_header,
            headers=resolved.parsed.headers,
            row_count=len(output_rows),
            column_count=resolved.parsed.column_count,
            output_rows=output_rows,
            output_csv=output_csv,
            formula_escape_count=formula_escape_count,
            replacements=replacements,
            output_intent=manifest.output_intent,
            share_policy=share_policy,
            summary=self._transform_summary(replacements, formula_escape_count),
        )

    def transform_job(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        request: CSVJobTransformRequest,
    ) -> CSVWorkflowResponse:
        _ = filename
        job = self.session.get(Job, request.job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if job.content_type is not ContentType.CSV:
            raise BadRequestError("Only CSV jobs can be transformed with this endpoint")

        csv_metadata = self._csv_job_metadata(job.findings)
        parsed = self._parse_csv(
            file_bytes,
            has_header=csv_metadata["has_header"],
            delimiter=csv_metadata["delimiter"],
            quotechar=csv_metadata["quotechar"],
        )

        stored_findings = {item.id: item for item in job.findings}
        for override in request.finding_overrides:
            self._apply_override(stored_findings, override)

        findings = [finding_to_schema(item) for item in job.findings]
        share_policy = build_text_share_policy(request.output_intent)
        output_rows, output_csv, replacements, formula_escape_count = self._apply_csv_findings(
            parsed=parsed,
            findings=findings,
            include_pending=request.include_pending,
            default_transformation=request.default_transformation,
            delimiter=csv_metadata["delimiter"],
            quotechar=csv_metadata["quotechar"],
            validate_cell_hash=True,
        )
        if request.persist_output:
            self._persist_csv_output(
                job_id=job.id,
                output_csv=output_csv,
                row_count=len(output_rows),
                column_count=parsed.column_count,
                replacement_count=len(replacements),
                formula_escape_count=formula_escape_count,
                has_header=parsed.has_header,
                output_intent=request.output_intent,
                share_policy=share_policy,
            )

        return CSVWorkflowResponse(
            job_id=job.id,
            findings=findings,
            has_header=parsed.has_header,
            headers=parsed.headers,
            row_count=len(output_rows),
            column_count=parsed.column_count,
            output_rows=output_rows,
            output_csv=output_csv,
            formula_escape_count=formula_escape_count,
            replacements=replacements,
            output_intent=request.output_intent,
            share_policy=share_policy,
            summary=self._transform_summary(replacements, formula_escape_count),
        )

    def _resolve_analysis(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: CSVWorkflowManifest,
    ) -> ResolvedCSVAnalysis:
        parsed = self._parse_csv(
            file_bytes,
            has_header=manifest.has_header,
            delimiter=manifest.delimiter,
            quotechar=manifest.quotechar,
        )
        (
            patterns,
            entities,
            pattern_ids,
            custom_entity_ids,
            configuration_ids,
            default_transformation,
            pii_detection,
        ) = self.text_detection.resolve_detection_context(
            content_type=ContentType.CSV,
            pattern_ids=manifest.pattern_ids,
            custom_entity_ids=manifest.custom_entity_ids,
            configuration_ids=manifest.configuration_ids,
            default_transformation=manifest.default_transformation,
            pii_detection=manifest.pii_detection,
        )
        findings = self._build_findings(
            parsed=parsed,
            apply_builtins=manifest.apply_builtins,
            exact_values=manifest.exact_values,
            patterns=patterns,
            entities=entities,
            default_transformation=default_transformation,
            pii_detection=pii_detection,
            delimiter=manifest.delimiter,
            quotechar=manifest.quotechar,
        )
        return ResolvedCSVAnalysis(
            title=manifest.title or Path(filename).name,
            parsed=parsed,
            findings=findings,
            pattern_ids=pattern_ids,
            custom_entity_ids=custom_entity_ids,
            configuration_ids=configuration_ids,
            default_transformation=default_transformation,
        )

    def _parse_csv(
        self,
        file_bytes: bytes,
        *,
        has_header: bool,
        delimiter: str,
        quotechar: str,
    ) -> ParsedCSV:
        text = self._decode_csv(file_bytes)
        reader = csv.reader(
            StringIO(text, newline=""),
            delimiter=delimiter,
            quotechar=quotechar,
            strict=True,
        )
        raw_rows = [list(row) for row in reader]
        if not raw_rows:
            raise BadRequestError("Uploaded CSV is empty")
        if len(raw_rows) > self.settings.max_csv_rows:
            raise PayloadTooLargeError(
                f"CSV exceeds the configured maximum row count of {self.settings.max_csv_rows}",
            )
        column_count = max((len(row) for row in raw_rows), default=0)
        if column_count > self.settings.max_csv_columns:
            raise PayloadTooLargeError(
                "CSV exceeds the configured maximum column count of "
                f"{self.settings.max_csv_columns}",
            )

        total_characters = 0
        for row in raw_rows:
            for cell in row:
                if len(cell) > self.settings.max_bulk_text_item_characters:
                    raise PayloadTooLargeError(
                        "CSV cell exceeds the configured maximum of "
                        f"{self.settings.max_bulk_text_item_characters} characters",
                    )
                total_characters += len(cell)
                if total_characters > self.settings.max_csv_characters:
                    raise PayloadTooLargeError(
                        "CSV exceeds the configured maximum character count of "
                        f"{self.settings.max_csv_characters}",
                    )

        header_row = raw_rows[0] if has_header else []
        data_rows = raw_rows[1:] if has_header else raw_rows
        physical_row_numbers = (
            list(range(2, len(raw_rows) + 1)) if has_header else list(range(1, len(raw_rows) + 1))
        )
        headers = self._resolve_headers(header_row, column_count, has_header)
        return ParsedCSV(
            has_header=has_header,
            headers=headers,
            rows=[list(row) for row in data_rows],
            physical_row_numbers=physical_row_numbers,
            column_count=column_count,
        )

    def _build_findings(
        self,
        *,
        parsed: ParsedCSV,
        apply_builtins: bool,
        exact_values: list[str],
        patterns: list[object],
        entities: list[object],
        default_transformation: TransformationRule | None,
        pii_detection: PIIDetectionOptions | None,
        delimiter: str,
        quotechar: str,
    ) -> list[FindingRecord]:
        findings: list[FindingRecord] = []
        for row_index, row in enumerate(parsed.rows):
            physical_row_number = parsed.physical_row_numbers[row_index]
            for column_index, cell in enumerate(row):
                if not cell:
                    continue
                cell_findings = self.text_detection.build_findings(
                    content=cell,
                    content_type=ContentType.CSV,
                    apply_builtins=apply_builtins,
                    exact_values=exact_values,
                    manual_spans=[],
                    patterns=patterns,
                    entities=entities,
                    default_transformation=default_transformation,
                    pii_detection=pii_detection,
                )
                column_name = self._column_name(parsed.headers, column_index)
                cell_hash = hash_value(cell)
                for finding in cell_findings:
                    metadata = dict(finding.metadata)
                    metadata.update(
                        {
                            "csv_kind": "csv",
                            "csv_has_header": parsed.has_header,
                            "csv_row_number": physical_row_number,
                            "csv_column_index": column_index + 1,
                            "csv_column_name": column_name,
                            "csv_cell_hash": cell_hash,
                            "csv_cell_character_count": len(cell),
                            "csv_delimiter": self._delimiter_label(delimiter),
                            "csv_quotechar": quotechar,
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

    def _apply_csv_findings(
        self,
        *,
        parsed: ParsedCSV,
        findings: list[FindingRecord],
        include_pending: bool,
        default_transformation: TransformationRule | None,
        delimiter: str,
        quotechar: str,
        validate_cell_hash: bool,
    ) -> tuple[list[list[str]], str, list[CSVReplacementRecord], int]:
        output_rows = [list(row) for row in parsed.rows]
        findings_by_cell: dict[tuple[int, int], list[FindingRecord]] = defaultdict(list)
        cell_hashes: dict[tuple[int, int], str] = {}
        column_names: dict[tuple[int, int], str] = {}

        for finding in findings:
            key = (self._csv_row_number(finding), self._csv_column_index(finding))
            findings_by_cell[key].append(finding)
            current_hash = self._csv_cell_hash(finding)
            existing_hash = cell_hashes.get(key)
            if existing_hash is not None and existing_hash != current_hash:
                raise UnprocessableContentError(
                    "Stored CSV finding metadata is internally inconsistent",
                )
            cell_hashes[key] = current_hash
            column_names[key] = self._csv_column_name(finding)

        row_map = {
            physical_row_number: row_index
            for row_index, physical_row_number in enumerate(parsed.physical_row_numbers)
        }
        replacements: list[CSVReplacementRecord] = []
        for (physical_row_number, column_index), cell_findings in findings_by_cell.items():
            row_index = row_map.get(physical_row_number)
            if row_index is None:
                raise UnprocessableContentError(
                    f"Resubmitted CSV is missing reviewed row {physical_row_number}",
                )
            row = output_rows[row_index]
            column_offset = column_index - 1
            if column_offset >= len(row):
                raise UnprocessableContentError(
                    "Resubmitted CSV is missing the reviewed cell at row "
                    f"{physical_row_number}, column {column_index}",
                )
            original_value = row[column_offset]
            if (
                validate_cell_hash
                and hash_value(original_value) != cell_hashes[(physical_row_number, column_index)]
            ):
                raise UnprocessableContentError(
                    "Resubmitted CSV cell content does not match the reviewed job at row "
                    f"{physical_row_number}, column {column_index}",
                )

            output_value, cell_replacements = self.text_transformations.apply_findings(
                content=original_value,
                findings=cell_findings,
                include_pending=include_pending,
                default_transformation=default_transformation,
            )
            row[column_offset] = output_value
            for replacement in cell_replacements:
                replacements.append(
                    CSVReplacementRecord(
                        entity_type=replacement.entity_type,
                        row_number=physical_row_number,
                        column_index=column_index,
                        column_name=column_names[(physical_row_number, column_index)],
                        start_index=replacement.start_index,
                        end_index=replacement.end_index,
                        original_preview=replacement.original_preview,
                        output_value=replacement.output_value,
                    ),
                )

        output_csv, formula_escape_count = self._serialize_csv(
            headers=parsed.headers,
            rows=output_rows,
            has_header=parsed.has_header,
            delimiter=delimiter,
            quotechar=quotechar,
        )
        return output_rows, output_csv, replacements, formula_escape_count

    def _serialize_csv(
        self,
        *,
        headers: list[str],
        rows: list[list[str]],
        has_header: bool,
        delimiter: str,
        quotechar: str,
    ) -> tuple[str, int]:
        buffer = StringIO(newline="")
        writer = csv.writer(
            buffer,
            delimiter=delimiter,
            quotechar=quotechar,
            lineterminator="\n",
        )
        formula_escape_count = 0
        if has_header:
            escaped_headers, escaped = self._escape_formula_cells(headers)
            writer.writerow(escaped_headers)
            formula_escape_count += escaped
        for row in rows:
            escaped_row, escaped = self._escape_formula_cells(row)
            writer.writerow(escaped_row)
            formula_escape_count += escaped
        return buffer.getvalue(), formula_escape_count

    def _escape_formula_cells(self, row: list[str]) -> tuple[list[str], int]:
        escaped_row: list[str] = []
        escape_count = 0
        for cell in row:
            if cell and cell.startswith(FORMULA_PREFIXES):
                escaped_row.append(f"'{cell}")
                escape_count += 1
            else:
                escaped_row.append(cell)
        return escaped_row, escape_count

    def _decode_csv(self, file_bytes: bytes) -> str:
        if not file_bytes:
            raise BadRequestError("Uploaded CSV is empty")
        try:
            return file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedMediaTypeError("CSV uploads must be UTF-8 or UTF-8 with BOM") from exc

    def _resolve_headers(self, row: list[str], column_count: int, has_header: bool) -> list[str]:
        if not has_header:
            return [f"column_{index}" for index in range(1, column_count + 1)]
        headers: list[str] = []
        for index in range(column_count):
            raw_value = row[index] if index < len(row) else ""
            headers.append(raw_value.strip() or f"column_{index + 1}")
        return headers

    def _column_name(self, headers: list[str], column_index: int) -> str:
        if column_index < len(headers):
            return headers[column_index]
        return f"column_{column_index + 1}"

    def _delimiter_label(self, delimiter: str) -> str:
        return "\\t" if delimiter == "\t" else delimiter

    def _csv_job_metadata(self, findings: list[JobFinding]) -> dict[str, object]:
        if not findings:
            raise UnprocessableContentError("CSV job has no persisted findings to transform")
        metadata = findings[0].extra_data
        has_header = metadata.get("csv_has_header")
        delimiter = metadata.get("csv_delimiter")
        quotechar = metadata.get("csv_quotechar")
        if (
            not isinstance(has_header, bool)
            or not isinstance(delimiter, str)
            or not isinstance(quotechar, str)
        ):
            raise UnprocessableContentError("CSV job is missing safe format metadata")
        resolved_delimiter = "\t" if delimiter == "\\t" else delimiter
        if resolved_delimiter not in {",", ";", "\t"} or len(quotechar) != 1:
            raise UnprocessableContentError("CSV job contains unsupported format metadata")
        return {
            "has_header": has_header,
            "delimiter": resolved_delimiter,
            "quotechar": quotechar,
        }

    def _csv_row_number(self, finding: FindingRecord) -> int:
        value = finding.metadata.get("csv_row_number")
        if not isinstance(value, int) or value < 1:
            raise UnprocessableContentError("CSV finding is missing safe row metadata")
        return value

    def _csv_column_index(self, finding: FindingRecord) -> int:
        value = finding.metadata.get("csv_column_index")
        if not isinstance(value, int) or value < 1:
            raise UnprocessableContentError("CSV finding is missing safe column metadata")
        return value

    def _csv_column_name(self, finding: FindingRecord) -> str:
        value = finding.metadata.get("csv_column_name")
        if not isinstance(value, str) or not value:
            raise UnprocessableContentError("CSV finding is missing safe column metadata")
        return value

    def _csv_cell_hash(self, finding: FindingRecord) -> str:
        value = finding.metadata.get("csv_cell_hash")
        if not isinstance(value, str) or not value:
            raise UnprocessableContentError("CSV finding is missing safe cell hash metadata")
        return value

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

    def _persist_csv_output(
        self,
        *,
        job_id: str,
        output_csv: str,
        row_count: int,
        column_count: int,
        replacement_count: int,
        formula_escape_count: int,
        has_header: bool,
        output_intent,
        share_policy,
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
                "output_hash": hash_value(output_csv),
                "row_count": row_count,
                "column_count": column_count,
                "replacement_count": replacement_count,
                "formula_escape_count": formula_escape_count,
                "csv_has_header": has_header,
                **share_metadata(output_intent, share_policy),
            },
        )
        self.session.add(output)
        self.session.commit()

    def _transform_summary(
        self,
        replacements: list[CSVReplacementRecord],
        formula_escape_count: int,
    ) -> dict[str, int]:
        return {
            "replacement_count": len(replacements),
            "transformed_cell_count": len(
                {(item.row_number, item.column_index) for item in replacements}
            ),
            "formula_escape_count": formula_escape_count,
        }
