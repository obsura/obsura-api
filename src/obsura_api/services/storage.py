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

    def read_stored_bytes(self, stored_path: str | Path) -> bytes:
        """Read a persisted file from the configured storage tree."""

        target = self.resolve_stored_path(stored_path)
        return target.read_bytes()

    def resolve_stored_path(self, stored_path: str | Path) -> Path:
        """Resolve a stored path and keep reads scoped to the configured storage root."""

        candidate = Path(stored_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate

        resolved = candidate.resolve(strict=False)
        storage_root = self.settings.storage_root.resolve()
        try:
            resolved.relative_to(storage_root)
        except ValueError as exc:
            raise ValueError("Stored path is outside the configured storage root") from exc
        if not resolved.exists():
            raise FileNotFoundError(f"Stored file does not exist: {resolved}")
        return resolved

    def media_url_for(self, path: Path) -> str:
        """Return a URL mounted by the FastAPI app for a stored file."""

        relative = path.relative_to(self.settings.storage_root).as_posix()
        return f"{self.settings.media_mount_path.rstrip('/')}/{relative}"
