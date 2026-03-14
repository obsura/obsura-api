"""Ephemeral storage service for sensitive uploads and generated outputs."""

from __future__ import annotations

import mimetypes
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Lock
from uuid import uuid4

from PIL import Image

from obsura_api.core.settings import Settings

OUTPUT_REFERENCE_PREFIX = "outputs/"
UPLOAD_REFERENCE_PREFIX = "uploads/"
OUTPUT_MEDIA_TYPE_BY_FORMAT = {
    "BMP": "image/bmp",
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "TIFF": "image/tiff",
    "WEBP": "image/webp",
}


@dataclass(slots=True)
class StoredArtifact:
    """One short-lived in-memory artifact."""

    content: bytes
    media_type: str
    expires_at: datetime


class StorageService:
    """Handle short-lived sensitive uploads and generated artifacts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._artifacts: OrderedDict[str, StoredArtifact] = OrderedDict()
        self._lock = Lock()
        self.ensure_directories()

    def ensure_directories(self) -> None:
        """Ensure the configured storage directories exist for legacy scrub paths."""

        self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        self.settings.upload_root.mkdir(parents=True, exist_ok=True)
        self.settings.output_root.mkdir(parents=True, exist_ok=True)

    def assert_ready(self) -> None:
        """Raise if the configured storage root is missing or not writable."""

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
        media_type: str | None = None,
    ) -> str:
        """Store a short-lived source artifact in memory."""

        target_suffix = self._normalize_suffix(suffix or Path(filename or "upload.bin").suffix or ".bin")
        reference = f"{UPLOAD_REFERENCE_PREFIX}{uuid4().hex}{target_suffix}"
        self._store_artifact(
            reference,
            content=file_bytes,
            media_type=media_type or self._media_type_for_suffix(target_suffix),
        )
        return reference

    def save_image(self, image: Image.Image, stem: str | None = None) -> str:
        """Store a short-lived generated image in memory."""

        extension = self.output_extension
        reference = f"{OUTPUT_REFERENCE_PREFIX}{self._safe_stem(stem)}.{extension}"
        content = self.render_image_bytes(image)
        self._store_artifact(
            reference,
            content=content,
            media_type=self.output_media_type,
        )
        return reference

    def render_image_bytes(self, image: Image.Image) -> bytes:
        """Render an image into the configured output format."""

        buffer = BytesIO()
        image.save(buffer, format=self.settings.image_output_format)
        return buffer.getvalue()

    def read_stored_bytes(self, stored_path: str | Path) -> bytes:
        """Read an artifact from memory or, for legacy refs, disk."""

        reference = self.storage_reference_for(stored_path)
        artifact = self._get_artifact(reference)
        if artifact is not None:
            return artifact.content
        target = self.resolve_stored_path(stored_path)
        return target.read_bytes()

    def get_media_type(self, stored_path: str | Path) -> str:
        """Resolve the content type for a stored artifact."""

        reference = self.storage_reference_for(stored_path)
        artifact = self._get_artifact(reference)
        if artifact is not None:
            return artifact.media_type
        return self._media_type_for_suffix(Path(reference).suffix)

    def resolve_stored_path(self, stored_path: str | Path) -> Path:
        """Resolve a legacy disk path scoped to the configured storage root."""

        reference = self.storage_reference_for(stored_path)
        if self._get_artifact(reference) is not None:
            raise ValueError("Stored artifact is ephemeral and has no filesystem path")

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
        """Return a URL for a short-lived generated output."""

        relative = self.storage_reference_for(path)
        if not self.is_public_reference(relative):
            raise ValueError("Only generated output artifacts can be exposed as media")
        return f"{self.settings.media_mount_path.rstrip('/')}/{relative}"

    def storage_reference_for(self, path: str | Path) -> str:
        """Return a normalized storage reference safe for API responses."""

        candidate = Path(path)
        normalized = candidate.as_posix().lstrip("/")
        if normalized in self._artifacts:
            return normalized

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

        if normalized.startswith(f"{storage_root.name}/"):
            return normalized.split("/", 1)[1]
        return normalized

    def is_public_reference(self, reference: str) -> bool:
        """Return whether a stored artifact may be served back to clients."""

        return reference.startswith(OUTPUT_REFERENCE_PREFIX)

    def purge_sensitive_storage(self) -> int:
        """Delete any previously persisted upload or output files from disk."""

        removed = 0
        for directory in (self.settings.upload_root, self.settings.output_root):
            if not directory.exists():
                continue
            for item in directory.rglob("*"):
                if not item.is_file():
                    continue
                item.unlink(missing_ok=True)
                removed += 1
        return removed

    @property
    def output_extension(self) -> str:
        return self.settings.image_output_format.lower()

    @property
    def output_media_type(self) -> str:
        return OUTPUT_MEDIA_TYPE_BY_FORMAT.get(
            self.settings.image_output_format.upper(),
            "application/octet-stream",
        )

    def _normalize_suffix(self, suffix: str) -> str:
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        sanitized = re.sub(r"[^A-Za-z0-9.]+", "", suffix).lower()
        return sanitized if sanitized not in {"", "."} else ".bin"

    def _safe_stem(self, stem: str | None) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", stem or "").strip("-")
        return normalized or uuid4().hex

    def _media_type_for_suffix(self, suffix: str) -> str:
        guessed = mimetypes.guess_type(f"artifact{suffix}")[0]
        return guessed or "application/octet-stream"

    def _store_artifact(
        self,
        reference: str,
        *,
        content: bytes,
        media_type: str,
    ) -> None:
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.ephemeral_artifact_ttl_seconds)
        with self._lock:
            self._sweep_expired_locked()
            self._artifacts[reference] = StoredArtifact(
                content=content,
                media_type=media_type,
                expires_at=expires_at,
            )
            self._artifacts.move_to_end(reference)
            while len(self._artifacts) > self.settings.max_ephemeral_artifacts:
                self._artifacts.popitem(last=False)

    def _get_artifact(self, reference: str) -> StoredArtifact | None:
        with self._lock:
            self._sweep_expired_locked()
            artifact = self._artifacts.get(reference)
            if artifact is None:
                return None
            self._artifacts.move_to_end(reference)
            return artifact

    def _sweep_expired_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [key for key, artifact in self._artifacts.items() if artifact.expires_at <= now]
        for key in expired:
            self._artifacts.pop(key, None)

    def _is_writable(self, directory: Path) -> bool:
        probe = directory / f".write-check-{uuid4().hex}"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False
