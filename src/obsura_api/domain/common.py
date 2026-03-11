"""Common Pydantic models shared across feature areas."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from obsura_api.domain.enums import SearchResultKind

T = TypeVar("T")


class TimestampedModel(BaseModel):
    """Base response model backed by SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class BoundingBox(BaseModel):
    """A region on an image or screenshot."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SearchResultItem(BaseModel):
    """Unified search result returned across saved assets and jobs."""

    kind: SearchResultKind
    id: str
    name: str
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)


class PaginationParams(BaseModel):
    """Shared pagination input for list-style endpoints."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginationMeta(BaseModel):
    """Pagination metadata returned alongside paged results."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ApiError(BaseModel):
    """Unified error payload."""

    code: str
    message: str
    details: Any | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Unified success or error envelope."""

    success: bool
    data: T | None = None
    pagination: PaginationMeta | None = None
    message: str | None = None
    error: ApiError | None = None


def build_pagination_meta(
    *,
    params: PaginationParams,
    total_items: int,
) -> PaginationMeta:
    """Build pagination metadata for a paged response."""

    total_pages = max(ceil(total_items / params.page_size), 1) if total_items else 1
    return PaginationMeta(
        page=params.page,
        page_size=params.page_size,
        total_items=total_items,
        total_pages=total_pages,
        has_next=params.page < total_pages,
        has_previous=params.page > 1,
    )
