"""Common Pydantic models shared across feature areas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from obsura_api.domain.enums import SearchResultKind


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

