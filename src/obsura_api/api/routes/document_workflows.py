"""Routes for PDF document workflows."""

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
from obsura_api.domain.documents import (
    DocumentJobTransformRequest,
    DocumentWorkflowManifest,
    DocumentWorkflowResponse,
)
from obsura_api.services.document_workflows import DocumentWorkflowService

router = APIRouter(prefix="/workflows/documents", tags=["document-workflows"])
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]
SUPPORTED_DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
}


def _parse_manifest_json(manifest_json: str) -> DocumentWorkflowManifest:
    try:
        return DocumentWorkflowManifest.model_validate_json(manifest_json)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _parse_transform_request_json(manifest_json: str) -> DocumentJobTransformRequest:
    try:
        return DocumentJobTransformRequest.model_validate_json(manifest_json)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _validate_upload(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    if content_type in SUPPORTED_DOCUMENT_CONTENT_TYPES:
        return
    if content_type in {"", "application/octet-stream"} and filename.endswith(".pdf"):
        return
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file content type. Only PDF uploads are supported",
    )


async def _read_upload_bytes(file: UploadFile, *, max_bytes: int) -> bytes:
    _validate_upload(file)

    chunks: list[bytes] = []
    total_size = 0
    try:
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
    finally:
        await file.close()

    file_bytes = b"".join(chunks)
    if not file_bytes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    return file_bytes


def _build_service(
    session: Session,
    settings: Settings,
    container: AppContainer,
) -> DocumentWorkflowService:
    return DocumentWorkflowService(
        session=session,
        settings=settings,
        document_extractor=container.document_extractor,
        pii_detector=container.pii_detector,
        text_anonymizer=container.text_anonymizer,
    )


@router.post("/analyze", response_model=ApiResponse[DocumentWorkflowResponse])
async def analyze_document(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[DocumentWorkflowResponse]:
    """Analyze an uploaded PDF into page-aware review findings."""

    manifest = _parse_manifest_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    return success_response(
        _build_service(session, settings, container).analyze(
            file_bytes=file_bytes,
            filename=file.filename or "document.pdf",
            manifest=manifest,
        ),
    )


@router.post("/transform", response_model=ApiResponse[DocumentWorkflowResponse])
async def transform_document(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[DocumentWorkflowResponse]:
    """Analyze and transform an uploaded PDF without persisting the raw document."""

    manifest = _parse_manifest_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    return success_response(
        _build_service(session, settings, container).transform(
            file_bytes=file_bytes,
            filename=file.filename or "document.pdf",
            manifest=manifest,
        ),
    )


@router.post("/transform-job", response_model=ApiResponse[DocumentWorkflowResponse])
async def transform_document_job(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[DocumentWorkflowResponse]:
    """Transform a reviewed PDF job using a resubmitted source file."""

    request = _parse_transform_request_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    return success_response(
        _build_service(session, settings, container).transform_job(
            file_bytes=file_bytes,
            filename=file.filename or "document.pdf",
            request=request,
        ),
    )
