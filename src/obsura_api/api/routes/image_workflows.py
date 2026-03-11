"""Routes for image-region workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_container, get_db_session, get_settings
from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings
from obsura_api.domain.workflows import ImageWorkflowManifest, ImageWorkflowResponse
from obsura_api.services.image_workflows import ImageWorkflowService

router = APIRouter(prefix="/workflows/images", tags=["image-workflows"])
SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[AppContainer, Depends(get_container)]


@router.post("/analyze", response_model=ImageWorkflowResponse)
async def analyze_image(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ImageWorkflowResponse:
    """Analyze an uploaded image or screenshot into reviewable regions."""

    manifest = ImageWorkflowManifest.model_validate_json(manifest_json)
    service = ImageWorkflowService(
        session=session,
        settings=settings,
        storage=container.storage,
        face_detector=container.face_detector,
    )
    return service.analyze(
        file_bytes=await file.read(),
        filename=file.filename or "upload.bin",
        manifest=manifest,
    )


@router.post("/transform", response_model=ImageWorkflowResponse)
async def transform_image(
    session: SessionDep,
    settings: SettingsDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    manifest_json: str = Form("{}"),
) -> ImageWorkflowResponse:
    """Apply image-region transformations and persist the generated output."""

    manifest = ImageWorkflowManifest.model_validate_json(manifest_json)
    service = ImageWorkflowService(
        session=session,
        settings=settings,
        storage=container.storage,
        face_detector=container.face_detector,
    )
    return service.transform(
        file_bytes=await file.read(),
        filename=file.filename or "upload.bin",
        manifest=manifest,
    )
