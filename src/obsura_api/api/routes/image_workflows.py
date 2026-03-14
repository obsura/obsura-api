"""Routes for image-region workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_container, get_db_session, get_settings
from obsura_api.api.responses import success_response
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings
from obsura_api.domain.common import ApiResponse
from obsura_api.domain.workflows import (
    ImageJobTransformRequest,
    ImageWorkflowManifest,
    ImageWorkflowResponse,
)
from obsura_api.services.image_workflows import ImageWorkflowService

router = APIRouter(prefix="/workflows/images", tags=["image-workflows"])
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]
SUPPORTED_IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
    "image/gif",
    "image/tiff",
}


def _parse_manifest_json(manifest_json: str) -> ImageWorkflowManifest:
    try:
        return ImageWorkflowManifest.model_validate_json(manifest_json)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _validate_upload(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    if content_type not in SUPPORTED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported file content type. Supported types: "
                + ", ".join(sorted(SUPPORTED_IMAGE_CONTENT_TYPES))
            ),
        )


async def _read_upload_bytes(file: UploadFile, *, max_bytes: int) -> bytes:
    _validate_upload(file)

    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Uploaded file exceeds the {max_bytes} byte limit",
            )
        chunks.append(chunk)

    file_bytes = b"".join(chunks)
    if not file_bytes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    return file_bytes


@router.post("/analyze", response_model=ApiResponse[ImageWorkflowResponse])
async def analyze_image(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[ImageWorkflowResponse]:
    """Analyze an uploaded image or screenshot into reviewable regions."""

    manifest = _parse_manifest_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    service = ImageWorkflowService(
        session=session,
        settings=settings,
        storage=container.storage,
        ocr_provider=container.ocr_provider,
        face_detector=container.face_detector,
        pii_detector=container.pii_detector,
    )
    return success_response(
        service.analyze(
            file_bytes=file_bytes,
            filename=file.filename or "upload.bin",
            manifest=manifest,
        ),
    )


@router.post("/transform", response_model=ApiResponse[ImageWorkflowResponse])
async def transform_image(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[ImageWorkflowResponse]:
    """Apply image-region transformations and persist the generated output."""

    manifest = _parse_manifest_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    service = ImageWorkflowService(
        session=session,
        settings=settings,
        storage=container.storage,
        ocr_provider=container.ocr_provider,
        face_detector=container.face_detector,
        pii_detector=container.pii_detector,
    )
    return success_response(
        service.transform(
            file_bytes=file_bytes,
            filename=file.filename or "upload.bin",
            manifest=manifest,
        ),
    )


@router.post("/transform-job", response_model=ApiResponse[ImageWorkflowResponse])
def transform_image_job(
    payload: ImageJobTransformRequest,
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> ApiResponse[ImageWorkflowResponse]:
    """Transform a persisted image or screenshot job after review decisions are applied."""

    service = ImageWorkflowService(
        session=session,
        settings=settings,
        storage=container.storage,
        ocr_provider=container.ocr_provider,
        face_detector=container.face_detector,
        pii_detector=container.pii_detector,
    )
    return success_response(service.transform_job(payload))
