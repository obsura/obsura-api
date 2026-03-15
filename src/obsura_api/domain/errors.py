"""Native application error types used below the API layer."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _status_code_to_code(status_code: int) -> str:
    member = HTTPStatus._value2member_map_.get(status_code)
    if member is None:
        return "application_error"
    return member.name.lower()


class AppError(Exception):
    """Base application error with HTTP-friendly metadata."""

    default_status_code = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        status_code: int | HTTPStatus | None = None,
        code: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        resolved_status = status_code or self.default_status_code
        self.status_code = int(resolved_status)
        self.code = code or _status_code_to_code(self.status_code)
        self.message = message
        self.details = details


class BadRequestError(AppError):
    """Raised when the request is structurally valid but semantically invalid."""

    default_status_code = HTTPStatus.BAD_REQUEST


class NotFoundError(AppError):
    """Raised when a requested application resource does not exist."""

    default_status_code = HTTPStatus.NOT_FOUND


class ConflictError(AppError):
    """Raised when the current deployment or resource state blocks the operation."""

    default_status_code = HTTPStatus.CONFLICT


class PayloadTooLargeError(AppError):
    """Raised when a request exceeds configured safety limits."""

    default_status_code = HTTPStatus(413)


class UnsupportedMediaTypeError(AppError):
    """Raised when an uploaded file or content type is unsupported."""

    default_status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE


class UnprocessableContentError(AppError):
    """Raised when safe validation fails against otherwise well-formed content."""

    default_status_code = HTTPStatus(422)
