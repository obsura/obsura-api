"""Image analysis and transformation workflows."""

from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException, status
from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy.orm import Session

from obsura_api.core.settings import Settings
from obsura_api.db.models import Job, JobFinding, JobOutput
from obsura_api.domain.enums import FindingKind, FindingSource, JobStatus, TransformationMode
from obsura_api.domain.transforms import TransformationRule
from obsura_api.domain.workflows import FindingRecord, ImageWorkflowManifest, ImageWorkflowResponse
from obsura_api.services.providers.faces import FaceDetector
from obsura_api.services.storage import StorageService
from obsura_api.services.studio import StudioService
from obsura_api.services.utils import summarize_findings


class ImageWorkflowService:
    """Analyze and transform image-region workflows."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        storage: StorageService,
        face_detector: FaceDetector,
    ) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage
        self.face_detector = face_detector
        self.studio = StudioService(session)

    def analyze(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: ImageWorkflowManifest,
    ) -> ImageWorkflowResponse:
        findings = self._build_findings(file_bytes, manifest)
        stored_input_path = None
        job_id = None
        if manifest.persist_job:
            stored_input = self.storage.save_upload(file_bytes, filename)
            stored_input_path = str(stored_input)
            job_id = self._persist_job(
                title=manifest.title,
                content_type=manifest.content_type,
                source_file_path=str(stored_input),
                findings=findings,
                configuration_ids=manifest.configuration_ids,
            )

        return ImageWorkflowResponse(
            job_id=job_id,
            findings=findings,
            stored_input_path=stored_input_path,
            summary=summarize_findings(findings),
        )

    def transform(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        manifest: ImageWorkflowManifest,
    ) -> ImageWorkflowResponse:
        image = Image.open(BytesIO(file_bytes)).convert("RGB")
        findings = self._build_findings(file_bytes, manifest)
        for finding in findings:
            if finding.region is None:
                continue
            rule = finding.transformation or TransformationRule(mode=TransformationMode.MASK)
            self._apply_region(image, finding, rule)

        stored_input_path = None
        job_id = None
        stored_output = self.storage.save_image(image)
        if manifest.persist_job:
            stored_input = self.storage.save_upload(file_bytes, filename)
            stored_input_path = str(stored_input)
            job_id = self._persist_job(
                title=manifest.title,
                content_type=manifest.content_type,
                source_file_path=str(stored_input),
                findings=findings,
                configuration_ids=manifest.configuration_ids,
                output_file_path=str(stored_output),
            )

        return ImageWorkflowResponse(
            job_id=job_id,
            findings=findings,
            stored_input_path=stored_input_path,
            stored_output_path=str(stored_output),
            media_url=self.storage.media_url_for(stored_output),
            summary=summarize_findings(findings),
        )

    def _build_findings(
        self,
        file_bytes: bytes,
        manifest: ImageWorkflowManifest,
    ) -> list[FindingRecord]:
        default_transformation = self._resolve_default_transformation(manifest.configuration_ids)
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
        return findings

    def _resolve_default_transformation(
        self,
        configuration_ids: list[str],
    ) -> TransformationRule | None:
        for configuration in self.studio.resolve_configurations(configuration_ids):
            if configuration.default_image_transformation:
                return TransformationRule.model_validate(configuration.default_image_transformation)
        return None

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

    def _persist_job(
        self,
        *,
        title: str | None,
        content_type: object,
        source_file_path: str,
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
