from __future__ import annotations

import hashlib

import pytest

from obsura_api.core.settings import Settings
from obsura_api.services.providers import text_anonymizer as anonymizer_module
from obsura_api.services.providers.text_anonymizer import build_text_anonymizer


def test_build_text_anonymizer_uses_native_backend_when_presidio_is_unavailable(monkeypatch) -> None:
    def raising_presidio_backend():
        raise RuntimeError("missing package")

    monkeypatch.setattr(anonymizer_module, "PresidioTextAnonymizer", raising_presidio_backend)
    settings = Settings(text_anonymizer_backend="auto", _env_file=None)

    backend = build_text_anonymizer(settings)

    assert backend.name == "native-text-anonymizer"
    assert backend.supported is True
    assert backend.hash_supported is False


def test_build_text_anonymizer_can_use_explicit_presidio_backend(monkeypatch) -> None:
    class StubTextAnonymizer:
        name = "presidio-text-anonymizer"
        supported = True
        hash_supported = True

        def replace(self, text: str, replacement: str) -> str:
            return replacement

        def mask(self, text: str, *, mask_character: str) -> str:
            return mask_character * len(text)

        def redact(self, text: str) -> str:
            return ""

        def hash(self, text: str, *, salt: str) -> str:
            return f"{salt}:{text}"

    monkeypatch.setattr(anonymizer_module, "PresidioTextAnonymizer", StubTextAnonymizer)
    settings = Settings(text_anonymizer_backend="presidio", _env_file=None)

    backend = build_text_anonymizer(settings)

    assert backend.name == "presidio-text-anonymizer"
    assert backend.supported is True
    assert backend.hash_supported is True


def test_native_text_anonymizer_hashes_with_deployment_salt() -> None:
    settings = Settings(
        text_anonymizer_backend="native",
        text_hash_salt="0123456789abcdef",
        _env_file=None,
    )

    backend = build_text_anonymizer(settings)

    assert backend.hash_supported is True
    assert backend.hash(text="secret", salt=settings.text_hash_salt or "") == hashlib.sha256(
        b"0123456789abcdef:secret",
    ).hexdigest()


def test_build_text_anonymizer_rejects_unknown_backend() -> None:
    settings = Settings(text_anonymizer_backend="mystery", _env_file=None)

    with pytest.raises(RuntimeError, match="Unsupported text anonymizer backend"):
        build_text_anonymizer(settings)
