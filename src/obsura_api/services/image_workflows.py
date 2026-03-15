"""Image analysis and transformation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobFinding, JobOutput
from obsura_api.domain.common import BoundingBox
from obsura_api.domain.enums import (
    ContentType,
    FindingKind,
    FindingSource,
    JobStatus,
    LabelFontFamily,
    LabelPosition,
    OverlayShape,
    ReviewDecision,
    TransformationMode,
)
from obsura_api.domain.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnprocessableContentError,
    UnsupportedMediaTypeError,
)
from obsura_api.domain.sharing import SharePolicySummary
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
from obsura_api.services.providers.pii import NoOpPIIDetector, PIIDetector
from obsura_api.services.sharing import (
    build_image_artifact,
    build_image_share_policy,
    resolve_image_transform_for_output_intent,
    share_metadata,
)
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
        security_rules_enforced = False
        auto_adjusted = False
        for finding in findings:
            if finding.region is None:
                continue
            resolved = resolve_image_transform_for_output_intent(
                finding=finding,
                finding_rule=finding.transformation,
                default_rule=None,
                output_intent=manifest.output_intent,
            )
            security_rules_enforced = security_rules_enforced or resolved.security_rules_enforced
            auto_adjusted = auto_adjusted or resolved.auto_adjusted
            self._apply_region(image, finding, resolved.rule)

        source_file_path = None
        job_id = None
        stored_output = self.storage.save_image(image)
        media_url = self.storage.media_url_for(stored_output)
        share_policy = build_image_share_policy(
            manifest.output_intent,
            security_rules_enforced=security_rules_enforced,
            auto_adjusted=auto_adjusted,
        )
        artifact = build_image_artifact(
            output_intent=manifest.output_intent,
            share_policy=share_policy,
            output_file_path=stored_output,
            media_url=media_url,
        )
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
                output_intent=manifest.output_intent,
                share_policy=share_policy,
                artifact=artifact,
            )

        return ImageWorkflowResponse(
            job_id=job_id,
            findings=findings,
            stored_input_path=None,
            stored_output_path=stored_output,
            media_url=media_url,
            output_intent=manifest.output_intent,
            share_policy=share_policy,
            artifacts=[artifact],
            summary=summarize_findings(findings),
        )

    def transform_job(self, request: ImageJobTransformRequest) -> ImageWorkflowResponse:
        """Transform a persisted image job using reviewed findings."""

        job = self.session.get(Job, request.job_id)
        if job is None:
            raise NotFoundError("Job not found")
        if job.content_type not in {ContentType.IMAGE, ContentType.SCREENSHOT}:
            raise BadRequestError(
                "Only image and screenshot jobs can be transformed with this endpoint",
            )
        if not job.source_file_path:
            raise BadRequestError(
                "Job does not retain a source image; resubmit the file to transform it",
            )

        stored_findings = {item.id: item for item in job.findings}
        for override in request.finding_overrides:
            self._apply_override(stored_findings, override)

        try:
            file_bytes = self.storage.read_stored_bytes(job.source_file_path)
        except FileNotFoundError as exc:
            raise NotFoundError("Stored source image was not found for this job") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

        image = self._sanitize_image_payload(file_bytes).image
        findings = [finding_to_schema(item) for item in job.findings]
        self._validate_findings_within_bounds(findings, image.size)
        default_transformation = self._resolve_default_transformation(job.configuration_ids)
        active_findings = self._active_findings(findings, request.include_pending)
        security_rules_enforced = False
        auto_adjusted = False

        for finding in active_findings:
            if finding.region is None:
                continue
            resolved = resolve_image_transform_for_output_intent(
                finding=finding,
                finding_rule=finding.transformation,
                default_rule=default_transformation,
                output_intent=request.output_intent,
            )
            security_rules_enforced = security_rules_enforced or resolved.security_rules_enforced
            auto_adjusted = auto_adjusted or resolved.auto_adjusted
            self._apply_region(image, finding, resolved.rule)

        stored_output = self.storage.save_image(image, stem=f"{job.id}-reviewed")
        media_url = self.storage.media_url_for(stored_output)
        share_policy = build_image_share_policy(
            request.output_intent,
            security_rules_enforced=security_rules_enforced,
            auto_adjusted=auto_adjusted,
        )
        artifact = build_image_artifact(
            output_intent=request.output_intent,
            share_policy=share_policy,
            output_file_path=stored_output,
            media_url=media_url,
        )
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
                    **share_metadata(request.output_intent, share_policy, artifact),
                },
            )
            self.session.add(output)
            self.session.commit()

        return ImageWorkflowResponse(
            job_id=job.id,
            findings=findings,
            stored_input_path=None,
            stored_output_path=stored_output,
            media_url=media_url,
            output_intent=request.output_intent,
            share_policy=share_policy,
            artifacts=[artifact],
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
                raise ConflictError(
                    "Automatic face detection is not configured for this deployment"
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
            raise ConflictError("Automatic OCR is not configured for this deployment")

        ocr_blocks = self.ocr_provider.extract_text(file_bytes)
        patterns, entities, text_default_transformation, pii_detection = (
            self.text_detection.resolve_transient_detection_context(
                content_type=ContentType.TEXT,
                pattern_ids=manifest.pattern_ids,
                custom_entity_ids=manifest.custom_entity_ids,
                configuration_ids=manifest.configuration_ids,
                pii_detection=manifest.pii_detection,
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
                pii_detection=pii_detection,
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
                            "ocr_text_hash": text_finding.matched_text_hash
                            or hash_value(block.text),
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
    ) -> TransformationRule | None:
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
        return None

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
                    raise UnsupportedMediaTypeError(
                        "Uploaded file is not a supported image format",
                    )
                if getattr(opened, "n_frames", 1) != 1:
                    raise BadRequestError("Animated or multi-frame images are not supported")
                width, height = opened.size
                if width * height > self.settings.max_image_pixels:
                    raise PayloadTooLargeError(
                        "Image exceeds the configured pixel limit of "
                        f"{self.settings.max_image_pixels}",
                    )
                opened.verify()

            with Image.open(BytesIO(file_bytes)) as opened:
                normalized = ImageOps.exif_transpose(opened)
                normalized.load()
                image = normalized.convert("RGB")
        except AppError:
            raise
        except Image.DecompressionBombError as exc:
            raise PayloadTooLargeError("Image is too large to process safely") from exc
        except UnidentifiedImageError as exc:
            raise BadRequestError("Uploaded file is not a valid image") from exc
        except OSError as exc:
            raise BadRequestError("Uploaded image could not be processed") from exc

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
        except AppError:
            raise
        except Image.DecompressionBombError as exc:
            raise PayloadTooLargeError("Image is too large to process safely") from exc
        except UnidentifiedImageError as exc:
            raise BadRequestError("Uploaded file is not a valid image") from exc
        except OSError as exc:
            raise BadRequestError("Uploaded image could not be processed") from exc

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
            raise UnprocessableContentError(
                f"Image region is outside the uploaded image bounds ({image_width}x{image_height})",
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

        box = self._expanded_box(image.size, finding.region, padding=rule.region_padding)
        region = image.crop(box)

        if rule.mode is TransformationMode.BLUR:
            transformed = region.filter(ImageFilter.GaussianBlur(radius=rule.blur_radius))
            self._paste_region(image, box, transformed, rule)
        elif rule.mode is TransformationMode.PIXELATE:
            region_width = max(box[2] - box[0], 1)
            region_height = max(box[3] - box[1], 1)
            reduced_width = max(1, region_width // rule.pixelation_scale)
            reduced_height = max(1, region_height // rule.pixelation_scale)
            transformed = region.resize((reduced_width, reduced_height)).resize(region.size)
            self._paste_region(image, box, transformed, rule)
        else:
            overlay = Image.new("RGBA", region.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            self._draw_shape(
                overlay_draw,
                self._local_box(region.size),
                rule,
                fill=rule.overlay_color,
            )
            composited = Image.alpha_composite(region.convert("RGBA"), overlay)
            image.paste(composited.convert("RGB"), box)

        self._decorate_region(image, box, rule)

    def _expanded_box(
        self,
        image_size: tuple[int, int],
        region: BoundingBox,
        *,
        padding: int,
    ) -> tuple[int, int, int, int]:
        image_width, image_height = image_size
        left = max(0, region.x - padding)
        top = max(0, region.y - padding)
        right = min(image_width, region.x + region.width + padding)
        bottom = min(image_height, region.y + region.height + padding)
        return (left, top, right, bottom)

    def _paste_region(
        self,
        image: Image.Image,
        box: tuple[int, int, int, int],
        transformed: Image.Image,
        rule: TransformationRule,
    ) -> None:
        if rule.overlay_shape is OverlayShape.RECTANGLE:
            image.paste(transformed, box)
            return
        mask = self._shape_mask(transformed.size, rule)
        image.paste(transformed, box, mask)

    def _shape_mask(self, size: tuple[int, int], rule: TransformationRule) -> Image.Image:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        self._draw_shape(draw, self._local_box(size), rule, fill=255)
        return mask

    def _local_box(self, size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = size
        return (0, 0, max(width - 1, 0), max(height - 1, 0))

    def _draw_shape(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        rule: TransformationRule,
        *,
        fill: str | int | None = None,
        outline: str | None = None,
        width: int = 0,
    ) -> None:
        if rule.overlay_shape is OverlayShape.ELLIPSE:
            draw.ellipse(box, fill=fill, outline=outline, width=width)
            return
        if rule.overlay_shape is OverlayShape.ROUNDED_RECTANGLE:
            max_radius = max(min(box[2] - box[0], box[3] - box[1]) // 2, 0)
            radius = min(rule.overlay_corner_radius, max_radius)
            draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
            return
        draw.rectangle(box, fill=fill, outline=outline, width=width)

    def _decorate_region(
        self,
        image: Image.Image,
        box: tuple[int, int, int, int],
        rule: TransformationRule,
    ) -> None:
        draw = ImageDraw.Draw(image)
        if rule.outline_color and rule.outline_width:
            self._draw_shape(
                draw,
                box,
                rule,
                outline=rule.outline_color,
                width=rule.outline_width,
            )

        label = self._resolve_overlay_label(rule)
        if not label:
            return

        font = self._load_font(rule)
        text_bounds = draw.textbbox((0, 0), label, font=font)
        text_width = text_bounds[2] - text_bounds[0]
        text_height = text_bounds[3] - text_bounds[1]
        label_width = text_width + (rule.label_padding * 2)
        label_height = text_height + (rule.label_padding * 2)
        label_left, label_top = self._label_origin(
            image.size,
            box,
            label_width=label_width,
            label_height=label_height,
            rule=rule,
        )
        background_box = (
            label_left,
            label_top,
            label_left + label_width,
            label_top + label_height,
        )
        if rule.label_background_color:
            draw.rounded_rectangle(
                background_box,
                radius=min(max(rule.label_padding * 2, 4), 12),
                fill=rule.label_background_color,
            )
        draw.text(
            (
                label_left + rule.label_padding - text_bounds[0],
                label_top + rule.label_padding - text_bounds[1],
            ),
            label,
            fill=rule.label_color,
            font=font,
        )

    def _resolve_overlay_label(self, rule: TransformationRule) -> str | None:
        if rule.overlay_label:
            return rule.overlay_label
        if rule.mode in {TransformationMode.CUSTOM, TransformationMode.GENERIC}:
            return rule.placeholder
        return None

    def _label_origin(
        self,
        image_size: tuple[int, int],
        box: tuple[int, int, int, int],
        *,
        label_width: int,
        label_height: int,
        rule: TransformationRule,
    ) -> tuple[int, int]:
        left, top, right, bottom = box
        if rule.label_position is LabelPosition.TOP_RIGHT:
            x = right - label_width - rule.label_margin
            y = top + rule.label_margin
        elif rule.label_position is LabelPosition.BOTTOM_LEFT:
            x = left + rule.label_margin
            y = bottom - label_height - rule.label_margin
        elif rule.label_position is LabelPosition.BOTTOM_RIGHT:
            x = right - label_width - rule.label_margin
            y = bottom - label_height - rule.label_margin
        elif rule.label_position is LabelPosition.CENTER:
            x = left + ((right - left - label_width) // 2)
            y = top + ((bottom - top - label_height) // 2)
        elif rule.label_position is LabelPosition.OUTSIDE_TOP:
            x = left + ((right - left - label_width) // 2)
            y = top - label_height - rule.label_margin
        elif rule.label_position is LabelPosition.OUTSIDE_BOTTOM:
            x = left + ((right - left - label_width) // 2)
            y = bottom + rule.label_margin
        else:
            x = left + rule.label_margin
            y = top + rule.label_margin

        image_width, image_height = image_size
        x = min(max(x, 0), max(image_width - label_width, 0))
        y = min(max(y, 0), max(image_height - label_height, 0))
        return x, y

    def _load_font(self, rule: TransformationRule) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        font_name = {
            LabelFontFamily.SANS: "DejaVuSans.ttf",
            LabelFontFamily.SERIF: "DejaVuSerif.ttf",
            LabelFontFamily.MONO: "DejaVuSansMono.ttf",
        }[rule.label_font_family]
        try:
            return ImageFont.truetype(font_name, rule.label_font_size)
        except OSError:
            return ImageFont.load_default()

    def _apply_override(
        self,
        stored_findings: dict[str, JobFinding],
        override: ImageFindingOverride,
    ) -> None:
        finding = stored_findings.get(override.finding_id)
        if finding is None:
            raise NotFoundError(f"Finding {override.finding_id} not found")
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
        output_intent=None,
        share_policy: SharePolicySummary | None = None,
        artifact=None,
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
                extra_data=(
                    share_metadata(output_intent, share_policy, artifact)
                    if output_intent is not None and share_policy is not None
                    else {}
                ),
            )
            self.session.add(output)

        self.session.commit()
        return job.id
