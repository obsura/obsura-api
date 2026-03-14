"""Application container for shared runtime objects."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from obsura_api.core.settings import Settings
from obsura_api.services.providers.faces import FaceDetector
from obsura_api.services.providers.ocr import OCRProvider
from obsura_api.services.providers.pii import PIIDetector
from obsura_api.services.storage import StorageService


@dataclass(slots=True)
class AppContainer:
    """Shared runtime container stored on the FastAPI application."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    storage: StorageService
    ocr_provider: OCRProvider
    face_detector: FaceDetector
    pii_detector: PIIDetector
