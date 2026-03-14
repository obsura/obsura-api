"""Text anonymizer backends for safe text replacement operators."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from obsura_api.core.settings import Settings


class TextAnonymizer(Protocol):
    """Protocol for text anonymization backends."""

    name: str
    supported: bool
    hash_supported: bool

    def replace(self, text: str, replacement: str) -> str:
        """Replace a text segment with a provided value."""

    def mask(self, text: str, *, mask_character: str) -> str:
        """Mask a text segment."""

    def redact(self, text: str) -> str:
        """Redact a text segment completely."""

    def hash(self, text: str, *, salt: str) -> str:
        """Hash a text segment with an explicit salt."""


class NativeTextAnonymizer:
    """Built-in text anonymizer that requires no optional dependencies."""

    name = "native-text-anonymizer"
    supported = True

    def __init__(self, *, hash_salt: str | None = None) -> None:
        self.hash_supported = bool(hash_salt)

    def replace(self, text: str, replacement: str) -> str:
        _ = text
        return replacement

    def mask(self, text: str, *, mask_character: str) -> str:
        return mask_character * max(len(text), 1)

    def redact(self, text: str) -> str:
        _ = text
        return ""

    def hash(self, text: str, *, salt: str) -> str:
        return _hash_with_salt(text, salt)


class PresidioTextAnonymizer:
    """Presidio-backed text anonymizer using vetted built-in operators only."""

    name = "presidio-text-anonymizer"
    supported = True
    hash_supported = True

    def __init__(self) -> None:
        try:
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig, RecognizerResult
        except ImportError as exc:
            raise RuntimeError(
                "Presidio text anonymization requires the `presidio-anonymizer` package.",
            ) from exc

        self._engine = AnonymizerEngine()
        self._operator_config = OperatorConfig
        self._recognizer_result = RecognizerResult

    def replace(self, text: str, replacement: str) -> str:
        return self._anonymize_segment(
            text,
            operator_name="replace",
            params={"new_value": replacement},
        )

    def mask(self, text: str, *, mask_character: str) -> str:
        return self._anonymize_segment(
            text,
            operator_name="mask",
            params={
                "masking_char": mask_character,
                "chars_to_mask": max(len(text), 1),
                "from_end": True,
            },
        )

    def redact(self, text: str) -> str:
        return self._anonymize_segment(text, operator_name="redact")

    def hash(self, text: str, *, salt: str) -> str:
        return self._anonymize_segment(
            text,
            operator_name="hash",
            params={"hash_type": "sha256", "salt": salt},
        )

    def _anonymize_segment(
        self,
        text: str,
        *,
        operator_name: str,
        params: dict[str, object] | None = None,
    ) -> str:
        if not text:
            return ""
        result = self._engine.anonymize(
            text=text,
            analyzer_results=[
                self._recognizer_result(
                    entity_type="TEXT",
                    start=0,
                    end=len(text),
                    score=1.0,
                )
            ],
            operators={
                "TEXT": self._operator_config(operator_name, params or {}),
            },
        )
        return result.text


def build_text_anonymizer(settings: Settings) -> TextAnonymizer:
    """Build the configured text anonymizer backend."""

    backend = settings.text_anonymizer_backend.strip().lower()
    if backend in {"native", "builtin", "built_in"}:
        return NativeTextAnonymizer(hash_salt=settings.text_hash_salt)
    if backend in {"presidio"}:
        return PresidioTextAnonymizer()
    if backend in {"", "auto"}:
        try:
            return PresidioTextAnonymizer()
        except RuntimeError:
            return NativeTextAnonymizer(hash_salt=settings.text_hash_salt)
    raise RuntimeError(
        f"Unsupported text anonymizer backend `{settings.text_anonymizer_backend}`.",
    )


def _hash_with_salt(text: str, salt: str) -> str:
    digest = hashlib.sha256()
    digest.update(salt.encode("utf-8"))
    digest.update(b":")
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
