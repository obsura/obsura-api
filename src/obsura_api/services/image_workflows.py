"""Image analysis and transformation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from fastapi import HTTPException, status
from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobFinding, JobOutput
from obsura_api.domain.enums import ContentType, FindingKind, FindingSource, JobStatus, ReviewDecision, TransformationMode
from obsura_api.domain.common import BoundingBox
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import (
    FindingRecord,
    ImageFindingOverride,
    ImageJobTransformRequest,
    ImageWorkflowManifest,
    ImageWorkflowResponse,
)

from obsura_api.services.detection import TextDetectionService
from obsura_api.services.jobs import finding_to_schema
from obsura_api.services.privacy import sanitize_persisted_finding_metadata
from obsura_api.services.providers.faces import FaceDetector
from obsura_api.services.providers.ocr import OCRBlock, OCRProvider
from obsura_api.services.providers.pii import PIIDetector, NoOpPIIDetector
from obsura_api.services.storage import StorageService
from obsura_api.services.studio import StudioService
from obsura_api.services.utils import hash_value, preview_value, summarize_findings


SUPPORTED_IMAGE_FORMATS = {"BMP", "GIF", "JPEG", "PNG", "TIFF", "WEBP"}


@dataclass(slots=True)
class SanitizedImagePayload:
    """A validated and metadata-stripped image payload."""

    image: Image.Image
    bytes: bytes
    media_type: str
    suffix: str


class ImageWorkflowService:
    """Analyze and transform image-region workflows."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        storage: StorageService,
        ocr_provider: OCRProvider,
        face_detector: FaceDetector,
        pii_detector: PIIDetector | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage
        self.ocr_provider = ocr_provider
        self.face_detector = face_detector
        self.studio = StudioService(session)
        self.text_detection = TextDetectionService(
            session,
            settings,
            pii_detector=pii_detector or NoOpPIIDetector(),
        )

    def analyze(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: ImageWorkflowManifest,
    ) -> ImageWorkflowResponse:
        payload = self._sanitize_image_payload(file_bytes)
        findings = self._build_findings(payload.bytes, manifest, image_size=payload.image.size)
        source_file_path = None
        job_id = None
        if manifest.persist_job:
            if self._should_persist_source_file(manifest):
                source_file_path = self.storage.save_upload(
                    payload.bytes,
                    filename,
                    suffix=payload.suffix,
                    media_type=payload.media_type,
                )
            job_id = self._persist_job(
                title=manifest.title,
                content_type=manifest.content_type,
                source_file_path=source_file_path,
                findings=findings,
                configuration_ids=manifest.configuration_ids,
            )

        return ImageWorkflowResponse(
            job_id=job_id,
            findings=findings,
            stored_input_path=None,
            summary=summarize_findings(findings),
        )

    def transform(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: ImageWorkflowManifest,
    ) -> ImageWorkflowResponse:
        payload = self._sanitize_image_payload(file_bytes)
        image = payload.image.copy()
        findings = self._build_findings(payload.bytes, manifest, image_size=image.size)
        for finding in findings:
            if finding.region is None:
                continue
            rule = finding.transformation or TransformationRule(mode=TransformationMode.MASK)
            self._apply_region(image, finding, rule)

        source_file_path = None
        job_id = None
        stored_output = self.storage.save_image(image)
        if manifest.persist_job:
            if self._should_persist_source_file(manifest):
                source_file_path = self.storage.save_upload(
                    payload.bytes,
                    filename,
                    suffix=payload.suffix,
                    media_type=payload.media_type,
                )
            job_id = self._persist_job(
                title=manifest.title,
                content_type=manifest.content_type,
                source_file_path=source_file_path,
                findings=findings,
                configuration_ids=manifest.configuration_ids,
                output_file_path=str(stored_output),
            )

        return ImageWorkflowResponse(
            job_id=job_id,
            findings=findings,
            stored_input_path=None,
            stored_output_path=stored_output,
            media_url=self.storage.media_url_for(stored_output),
            summary=summarize_findings(findings),
        )

    def transform_job(self, request: ImageJobTransformRequest) -> ImageWorkflowResponse:
        """Transform a persisted image job using reviewed findings."""

        job = self.session.get(Job, request.job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.content_type not in {ContentType.IMAGE, ContentType.SCREENSHOT}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Only image and screenshot jobs can be transformed with this endpoint",
            )
        if not job.source_file_path:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Job does not retain a source image; resubmit the file to transform it",
            )

        stored_findings = {item.id: item for item in job.findings}
        for override in request.finding_overrides:
            self._apply_override(stored_findings, override)

        try:
            file_bytes = self.storage.read_stored_bytes(job.source_file_path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Stored source image was not found for this job",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        image = self._sanitize_image_payload(file_bytes).image
        findings = [finding_to_schema(item) for item in job.findings]
        self._validate_findings_within_bounds(findings, image.size)
        default_transformation = self._resolve_default_transformation(job.configuration_ids)
        active_findings = self._active_findings(findings, request.include_pending)

        for finding in active_findings:
            if finding.region is None:
                continue
            rule = finding.transformation or default_transformation or TransformationRule(
                mode=TransformationMode.MASK,
            )
            self._apply_region(image, finding, rule)

        stored_output = self.storage.save_image(image, stem=f"{job.id}-reviewed")
        if request.persist_output:
            job.status = JobStatus.TRANSFORMED
            job.summary = summarize_findings(findings)
            output = JobOutput(
                job_id=job.id,
                content_type=job.content_type,
                output_file_path=str(stored_output),
                extra_data={
                    "source_output": "reviewed-job-transform",
                    "applied_finding_count": len(active_findings),
                },
            )
            self.session.add(output)
            self.session.commit()

        return ImageWorkflowResponse(
            job_id=job.id,
            findings=findings,
            stored_input_path=None,
            stored_output_path=stored_output,
            media_url=self.storage.media_url_for(stored_output),
            summary=summarize_findings(findings),
        )

    def _build_findings(
        self,
        file_bytes: bytes,
        manifest: ImageWorkflowManifest,
        *,
        image_size: tuple[int, int],
    ) -> list[FindingRecord]:
        default_transformation = self._resolve_default_transformation(
            manifest.configuration_ids,
            manifest.default_transformation,
        )
        findings: list[FindingRecord] = []
        for region in manifest.regions:
            findings.append(
                FindingRecord(
                    source=region.source,
                    kind=region.kind,
                    entity_type=region.entity_type,
                    entity_name=region.entity_name,
                    region=region.region,
                    transformation=region.transformation or default_transformation,
                    metadata=region.metadata,
                ),
            )

        if manifest.detect_text:
            findings.extend(
                self._build_ocr_findings(
                    file_bytes=file_bytes,
                    manifest=manifest,
                    default_transformation=default_transformation,
                ),
            )

        if manifest.detect_faces:
            if not self.face_detector.supported:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Automatic face detection is not configured for this deployment",
                )
            for face in self.face_detector.detect_faces(file_bytes):
                findings.append(
                    FindingRecord(
                        source=FindingSource.FACE,
                        kind=FindingKind.FACE_REGION,
                        entity_type="FACE",
                        entity_name="Detected face",
                        region=face.region,
                        confidence=face.confidence,
                        transformation=default_transformation
                        or TransformationRule(mode=TransformationMode.BLUR),
                    ),
                )
                for name, region in face.subregions.items():
                    findings.append(
                        FindingRecord(
                            source=FindingSource.FACE,
                            kind=FindingKind.FACE_SUBREGION,
                            entity_type=name.upper(),
                            entity_name=name,
                            region=region,
                            confidence=face.confidence,
                            transformation=default_transformation
                            or TransformationRule(
                                mode=TransformationMode.BLUR,
                                blur_radius=12,
                            ),
                        ),
                    )
        self._validate_findings_within_bounds(findings, image_size)
        return findings

    def _resolve_default_transformation(
        self,
        configuration_ids: list[str],
        request_default: TransformationRule | None = None,
    ) -> TransformationRule | None:
        if request_default is not None:
            return request_default
        for configuration in self.studio.resolve_configurations(configuration_ids):
            if configuration.default_image_transformation:
                return TransformationRule.model_validate(configuration.default_image_transformation)
        return None

    def _build_ocr_findings(
        self,
        *,
        file_bytes: bytes,
        manifest: ImageWorkflowManifest,
        default_transformation: TransformationRule | None,
    ) -> list[FindingRecord]:
        if not self.ocr_provider.supported:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Automatic OCR is not configured for this deployment",
            )

        ocr_blocks = self.ocr_provider.extract_text(file_bytes)
        patterns, entities, text_default_transformation = (
            self.text_detection.resolve_transient_detection_context(
                content_type=ContentType.TEXT,
                pattern_ids=manifest.pattern_ids,
                custom_entity_ids=manifest.custom_entity_ids,
                configuration_ids=manifest.configuration_ids,
            )
        )
        findings: list[FindingRecord] = []
        for block in ocr_blocks:
            text_findings = self.text_detection.build_findings(
                content=block.text,
                content_type=ContentType.TEXT,
                apply_builtins=manifest.apply_builtins,
                exact_values=manifest.exact_values,
                manual_spans=[],
                patterns=patterns,
                entities=entities,
                default_transformation=text_default_transformation,
            )
            for text_finding in text_findings:
                region = self._region_for_text_finding(block, text_finding)
                matched_preview = text_finding.matched_text_preview or preview_value(block.text)
                findings.append(
                    FindingRecord(
                        source=FindingSource.OCR,
                        kind=FindingKind.IMAGE_REGION,
                        entity_type=text_finding.entity_type,
                        entity_name=text_finding.entity_name,
                        region=region,
                        matched_text_preview=matched_preview,
                        matched_text_hash=text_finding.matched_text_hash or hash_value(block.text),
                        confidence=block.confidence,
                        transformation=self._visual_transformation_for_finding(
                            text_finding.transformation,
                            default_transformation,
                        ),
                        metadata={
                            "ocr_confidence": int(round(block.confidence * 100)),
                            "ocr_detection_source": text_finding.source.value,
                            "ocr_text_hash": text_finding.matched_text_hash or hash_value(block.text),
                            "ocr_token_count": len(block.tokens),
                        },
                    ),
                )
        return findings

    def _region_for_text_finding(
        self,
        block: OCRBlock,
        finding: FindingRecord,
    ) -> BoundingBox:
        if not block.tokens or finding.start_index is None or finding.end_index is None:
            return block.region

        matched_regions: list[BoundingBox] = []
        cursor = 0
        for index, token in enumerate(block.tokens):
            if index > 0:
                cursor += 1
            token_start = cursor
            token_end = token_start + len(token.text)
            if finding.start_index < token_end and finding.end_index > token_start:
                matched_regions.append(token.region)
            cursor = token_end

        if not matched_regions:
            return block.region
        return self._combine_regions(matched_regions)

    def _visual_transformation_for_finding(
        self,
        raw_transformation: TransformationRule | None,
        default_transformation: TransformationRule | None,
    ) -> TransformationRule:
        if raw_transformation is not None and raw_transformation.mode in {
            TransformationMode.MASK,
            TransformationMode.BLUR,
            TransformationMode.PIXELATE,
            TransformationMode.OVERLAY,
            TransformationMode.IMAGE_REPLACEMENT,
        }:
            return raw_transformation
        if default_transformation is not None:
            return default_transformation
        return TransformationRule(mode=TransformationMode.MASK)

    def _combine_regions(self, regions: Iterable[BoundingBox]) -> BoundingBox:
        items = list(regions)
        if not items:
            return BoundingBox(x=0, y=0, width=0, height=0)

        left = min(item.x for item in items)
        top = min(item.y for item in items)
        right = max(item.x + item.width for item in items)
        bottom = max(item.y + item.height for item in items)
        return BoundingBox(
            x=left,
            y=top,
            width=right - left,
            height=bottom - top,
        )

    def _sanitize_image_payload(self, file_bytes: bytes) -> SanitizedImagePayload:
        try:
            with Image.open(BytesIO(file_bytes)) as opened:
                image_format = (opened.format or "").upper()
                if image_format not in SUPPORTED_IMAGE_FORMATS:
                    raise HTTPException(
                        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Uploaded file is not a supported image format",
                    )
                if getattr(opened, "n_frames", 1) != 1:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="Animated or multi-frame images are not supported",
                    )
                width, height = opened.size
                if width * height > self.settings.max_image_pixels:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            "Image exceeds the configured pixel limit of "
                            f"{self.settings.max_image_pixels}"
                        ),
                    )
                opened.verify()

            with Image.open(BytesIO(file_bytes)) as opened:
                normalized = ImageOps.exif_transpose(opened)
                normalized.load()
                image = normalized.convert("RGB")
        except HTTPException:
            raise
        except Image.DecompressionBombError as exc:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image is too large to process safely",
            ) from exc
        except UnidentifiedImageError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is not a valid image",
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image could not be processed",
            ) from exc

        suffix = f".{self.storage.output_extension}"
        return SanitizedImagePayload(
            image=image,
            bytes=self.storage.render_image_bytes(image),
            media_type=self.storage.output_media_type,
            suffix=suffix,
        )

    def _load_image(self, file_bytes: bytes) -> Image.Image:
        try:
            with Image.open(BytesIO(file_bytes)) as opened:
                opened.load()
                return opened.convert("RGB")
        except HTTPException:
            raise
        except Image.DecompressionBombError as exc:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image is too large to process safely",
            ) from exc
        except UnidentifiedImageError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is not a valid image",
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image could not be processed",
            ) from exc

    def _validate_findings_within_bounds(
        self,
        findings: list[FindingRecord],
        image_size: tuple[int, int],
    ) -> None:
        for finding in findings:
            if finding.region is None:
                continue
            self._validate_region(finding.region, image_size)

    def _validate_region(
        self,
        region: BoundingBox,
        image_size: tuple[int, int],
    ) -> None:
        image_width, image_height = image_size
        if region.x + region.width > image_width or region.y + region.height > image_height:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Image region is outside the uploaded image bounds "
                    f"({image_width}x{image_height})"
                ),
            )

    def _should_persist_source_file(self, manifest: ImageWorkflowManifest) -> bool:
        if manifest.persist_source_content is not None:
            return manifest.persist_source_content
        return True

    def _apply_region(
        self,
        image: Image.Image,
        finding: FindingRecord,
        rule: TransformationRule,
    ) -> None:
        if finding.region is None:
            return

        left = finding.region.x
        top = finding.region.y
        right = left + finding.region.width
        bottom = top + finding.region.height
        box = (left, top, right, bottom)
        region = image.crop(box)

        if rule.mode is TransformationMode.BLUR:
            transformed = region.filter(ImageFilter.GaussianBlur(radius=rule.blur_radius))
            image.paste(transformed, box)
            return

        if rule.mode is TransformationMode.PIXELATE:
            reduced_width = max(1, finding.region.width // rule.pixelation_scale)
            reduced_height = max(1, finding.region.height // rule.pixelation_scale)
            transformed = region.resize((reduced_width, reduced_height)).resize(region.size)
            image.paste(transformed, box)
            return

        draw = ImageDraw.Draw(image)
        draw.rectangle(box, fill=rule.overlay_color)
        label = rule.overlay_label or rule.placeholder or finding.entity_name
        if label:
            draw.text((left + 4, top + 4), label, fill="white")

    def _apply_override(
        self,
        stored_findings: dict[str, JobFinding],
        override: ImageFindingOverride,
    ) -> None:
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

    def _active_findings(
        self,
        findings: list[FindingRecord],
        include_pending: bool,
    ) -> list[FindingRecord]:
        return [
            item
            for item in findings
            if item.region is not None
            and (
                item.decision is ReviewDecision.APPROVED
                or (include_pending and item.decision is ReviewDecision.PENDING)
            )
        ]

    def _persist_job(
        self,
        *,
        title: str | None,
        content_type: object,
        source_file_path: str | None,
        findings: list[FindingRecord],
        configuration_ids: list[str],
        output_file_path: str | None = None,
    ) -> str:
        job = Job(
            title=title,
            status=JobStatus.TRANSFORMED if output_file_path else JobStatus.ANALYZED,
            content_type=content_type,
            source_file_path=source_file_path,
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
                region=finding.region.model_dump() if finding.region else None,
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

        if output_file_path:
            output = JobOutput(
                job_id=job.id,
                content_type=job.content_type,
                output_file_path=output_file_path,
                extra_data={},
            )
            self.session.add(output)

        self.session.commit()
        return job.id
