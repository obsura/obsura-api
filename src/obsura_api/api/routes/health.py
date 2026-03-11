"""Health and metadata endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from obsura_api.api.responses import success_response
from obsura_api.domain.common import ApiResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def healthcheck() -> ApiResponse[dict[str, str]]:
    """Simple liveness response."""

    return success_response({"status": "ok"})
