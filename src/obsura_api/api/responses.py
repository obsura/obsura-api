"""Unified API response helpers and exception handlers."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from obsura_api.domain.common import ApiError, ApiResponse, PaginationMeta

logger = logging.getLogger(__name__)


def _sanitize_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_details(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_details(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_details(item) for item in value]
    if isinstance(value, Exception):
        return str(value)
    return value


def success_response(
    data: Any,
    *,
    pagination: PaginationMeta | None = None,
    message: str | None = None,
) -> ApiResponse[Any]:
    """Build a successful unified API response."""

    return ApiResponse[Any](
        success=True,
        data=data,
        pagination=pagination,
        message=message,
    )


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    """Build a failed unified API response."""

    payload = ApiResponse[Any](
        success=False,
        error=ApiError(code=code, message=message, details=_sanitize_details(details)),
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(
            mode="json",
            exclude_none=True,
            fallback=lambda value: str(value),
        ),
    )


def http_exception_handler(
    request: Request,
    exc: HTTPException | StarletteHTTPException,
) -> JSONResponse:
    """Return FastAPI HTTP exceptions in the unified error envelope."""

    _ = request
    status_name = (
        HTTPStatus(exc.status_code).name.lower()
        if exc.status_code in HTTPStatus._value2member_map_
        else "http_error"
    )
    details = exc.detail if isinstance(exc.detail, (list, dict)) else None
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return error_response(
        status_code=exc.status_code,
        code=status_name,
        message=message,
        details=details,
    )


def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return request validation errors in the unified envelope."""

    _ = request
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        message="Request validation failed",
        details=exc.errors(),
    )


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return unexpected exceptions in the unified envelope."""

    logger.exception("Unhandled application error on %s %s", request.method, request.url.path)
    return error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="Internal server error",
    )
