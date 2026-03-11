"""Local storage service for uploaded files and generated outputs."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from PIL import Image

from obsura_api.core.settings import Settings


class StorageService:
    """Handle local file persistence for uploads and generated artifacts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ensure_directories()

    def ensure_directories(self) -> None:
        """Ensure the configured storage directories exist."""

        self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        self.settings.upload_root.mkdir(parents=True, exist_ok=True)
        self.settings.output_root.mkdir(parents=True, exist_ok=True)

    def assert_ready(self) -> None:
        """Raise if storage directories are missing or not writable."""

        self.ensure_directories()
        for directory in (
            self.settings.storage_root,
            self.settings.upload_root,
            self.settings.output_root,
        ):
            if not directory.is_dir():
                raise RuntimeError(f"Storage path is not a directory: {directory}")
            if not self._is_writable(directory):
                raise RuntimeError(f"Storage path is not writable: {directory}")

    def save_upload(
        self,
        file_bytes: bytes,
        filename: str | None = None,
        *,
        suffix: str | None = None,
    ) -> Path:
        """Persist an uploaded source file and return its path."""

        target_suffix = self._normalize_suffix(suffix or Path(filename or "upload.bin").suffix or ".bin")
        target = (self.settings.upload_root / f"{uuid4().hex}{target_suffix}").resolve()
        target.write_bytes(file_bytes)
        return target

    def save_image(self, image: Image.Image, stem: str | None = None) -> Path:
        """Persist a generated image and return its path."""

        extension = self.settings.image_output_format.lower()
        safe_stem = self._safe_stem(stem) if stem else uuid4().hex
        target = (self.settings.output_root / f"{safe_stem}.{extension}").resolve()
        image.save(target, format=self.settings.image_output_format)
        return target

    def read_stored_bytes(self, stored_path: str | Path) -> bytes:
        """Read a persisted file from the configured storage tree."""

        target = self.resolve_stored_path(stored_path)
        return target.read_bytes()

    def resolve_stored_path(self, stored_path: str | Path) -> Path:
        """Resolve a stored path and keep reads scoped to the configured storage root."""

        candidate = Path(stored_path)
        storage_root = self.settings.storage_root.resolve()
        candidates: list[Path] = [candidate]
        if not candidate.is_absolute():
            candidates.insert(0, self.settings.storage_root / candidate)

        for option in candidates:
            resolved = option.resolve(strict=False)
            try:
                resolved.relative_to(storage_root)
            except ValueError:
                continue
            if resolved.exists():
                return resolved

        resolved = candidates[0].resolve(strict=False)
        try:
            resolved.relative_to(storage_root)
        except ValueError as exc:
            raise ValueError("Stored path is outside the configured storage root") from exc
        raise FileNotFoundError(f"Stored file does not exist: {resolved}")

    def media_url_for(self, path: str | Path) -> str:
        """Return a URL mounted by the FastAPI app for a stored file."""

        relative = self.storage_reference_for(path)
        return f"{self.settings.media_mount_path.rstrip('/')}/{relative}"

    def storage_reference_for(self, path: str | Path) -> str:
        """Return a storage-root relative reference safe for API responses."""

        candidate = Path(path)
        storage_root = self.settings.storage_root.resolve()
        resolved_candidates: list[Path] = []
        if candidate.is_absolute():
            resolved_candidates.append(candidate.resolve(strict=False))
        else:
            resolved_candidates.append((self.settings.storage_root / candidate).resolve(strict=False))
            resolved_candidates.append(candidate.resolve(strict=False))

        for resolved in resolved_candidates:
            try:
                return resolved.relative_to(storage_root).as_posix()
            except ValueError:
                continue

        normalized = candidate.as_posix().lstrip("/")
        if normalized.startswith(f"{storage_root.name}/"):
            return normalized.split("/", 1)[1]
        return normalized

    def _normalize_suffix(self, suffix: str) -> str:
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        sanitized = re.sub(r"[^A-Za-z0-9.]+", "", suffix).lower()
        return sanitized if sanitized not in {"", "."} else ".bin"

    def _safe_stem(self, stem: str | None) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", stem or "").strip("-")
        return normalized or uuid4().hex

    def _is_writable(self, directory: Path) -> bool:
        probe = directory / f".write-check-{uuid4().hex}"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False
