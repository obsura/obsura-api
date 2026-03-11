"""Local storage service for uploaded files and generated outputs."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image

from obsura_api.core.settings import Settings


class StorageService:
    """Handle local file persistence for uploads and generated artifacts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        self.settings.upload_root.mkdir(parents=True, exist_ok=True)
        self.settings.output_root.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file_bytes: bytes, filename: str | None = None) -> Path:
        """Persist an uploaded source file and return its path."""

        suffix = Path(filename or "upload.bin").suffix or ".bin"
        target = self.settings.upload_root / f"{uuid4().hex}{suffix}"
        target.write_bytes(file_bytes)
        return target

    def save_image(self, image: Image.Image, stem: str | None = None) -> Path:
        """Persist a generated image and return its path."""

        extension = self.settings.image_output_format.lower()
        target = self.settings.output_root / f"{stem or uuid4().hex}.{extension}"
        image.save(target, format=self.settings.image_output_format)
        return target

    def media_url_for(self, path: Path) -> str:
        """Return a URL mounted by the FastAPI app for a stored file."""

        relative = path.relative_to(self.settings.storage_root).as_posix()
        return f"{self.settings.media_mount_path.rstrip('/')}/{relative}"

