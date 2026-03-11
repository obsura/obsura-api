"""FastAPI dependencies shared across routers."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Query, Request
from sqlalchemy.orm import Session

from obsura_api.core.container import AppContainer
from obsura_api.core.settings import Settings
from obsura_api.domain.common import PaginationParams


def get_container(request: Request) -> AppContainer:
    """Return the shared application container."""

    return request.app.state.container


def get_settings(request: Request) -> Settings:
    """Return the current runtime settings."""

    return get_container(request).settings


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Open a database session for the current request."""

    container = get_container(request)
    session = container.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_pagination_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginationParams:
    """Parse shared pagination query parameters."""

    return PaginationParams(page=page, page_size=page_size)
