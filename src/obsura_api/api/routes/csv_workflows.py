"""Routes for CSV workflows."""

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
from obsura_api.domain.csv_workflows import (
    CSVJobTransformRequest,
    CSVWorkflowManifest,
    CSVWorkflowResponse,
)
from obsura_api.services.csv_workflows import CSVWorkflowService

router = APIRouter(prefix="/workflows/csv", tags=["csv-workflows"])
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]
SUPPORTED_CSV_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
}


def _parse_manifest_json(manifest_json: str) -> CSVWorkflowManifest:
    try:
        return CSVWorkflowManifest.model_validate_json(manifest_json)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _parse_transform_request_json(manifest_json: str) -> CSVJobTransformRequest:
    try:
        return CSVJobTransformRequest.model_validate_json(manifest_json)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _validate_upload(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    if content_type in SUPPORTED_CSV_CONTENT_TYPES:
        return
    if content_type in {"", "application/octet-stream"} and filename.endswith(".csv"):
        return
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file content type. Only CSV uploads are supported",
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
) -> CSVWorkflowService:
    return CSVWorkflowService(
        session=session,
        settings=settings,
        pii_detector=container.pii_detector,
        text_anonymizer=container.text_anonymizer,
    )


@router.post(
    "/analyze",
    response_model=ApiResponse[CSVWorkflowResponse],
    summary="Analyze CSV",
)
async def analyze_csv(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[CSVWorkflowResponse]:
    """Analyze an uploaded CSV into reviewable cell findings."""

    manifest = _parse_manifest_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    return success_response(
        _build_service(session, settings, container).analyze(
            file_bytes=file_bytes,
            filename=file.filename or "upload.csv",
            manifest=manifest,
        ),
    )


@router.post(
    "/transform",
    response_model=ApiResponse[CSVWorkflowResponse],
    summary="Transform CSV",
)
async def transform_csv(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[CSVWorkflowResponse]:
    """Analyze and transform an uploaded CSV without persisting raw file contents."""

    manifest = _parse_manifest_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    return success_response(
        _build_service(session, settings, container).transform(
            file_bytes=file_bytes,
            filename=file.filename or "upload.csv",
            manifest=manifest,
        ),
    )


@router.post(
    "/transform-job",
    response_model=ApiResponse[CSVWorkflowResponse],
    summary="Transform CSV Job",
)
async def transform_csv_job(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ApiResponse[CSVWorkflowResponse]:
    """Transform a reviewed CSV job using a resubmitted source file."""

    request = _parse_transform_request_json(manifest_json)
    file_bytes = await _read_upload_bytes(file, max_bytes=settings.max_upload_bytes)
    return success_response(
        _build_service(session, settings, container).transform_job(
            file_bytes=file_bytes,
            filename=file.filename or "upload.csv",
            request=request,
        ),
    )
