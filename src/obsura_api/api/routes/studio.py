"""Routes for saved studio assets and search."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_db_session, get_pagination_params
from obsura_api.api.responses import success_response
from obsura_api.domain.common import ApiResponse, PaginationParams, SearchResultItem
from obsura_api.domain.studio import (
    ConfigurationCreate,
    ConfigurationRead,
    ConfigurationUpdate,
    CustomEntityCreate,
    CustomEntityRead,
    CustomEntityUpdate,
    PatternCreate,
    PatternFromSelectionRequest,
    PatternRead,
    PatternUpdate,
)
from obsura_api.services.search import SearchService
from obsura_api.services.studio import StudioService

router = APIRouter(prefix="/studio", tags=["studio"])
SessionDep = Annotated[Session, Depends(get_db_session)]
PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]


@router.post("/patterns", response_model=ApiResponse[PatternRead], status_code=201)
def create_pattern(payload: PatternCreate, session: SessionDep) -> ApiResponse[PatternRead]:
    """Create a reusable detection pattern with an optional default transformation."""

    return success_response(StudioService(session).create_pattern(payload))


@router.get("/patterns", response_model=ApiResponse[list[PatternRead]])
def list_patterns(
    session: SessionDep,
    pagination: PaginationDep,
) -> ApiResponse[list[PatternRead]]:
    """List saved patterns in reverse creation order."""

    items, pagination_meta = StudioService(session).list_patterns(pagination)
    return success_response(items, pagination=pagination_meta)


@router.get("/patterns/{pattern_id}", response_model=ApiResponse[PatternRead])
def get_pattern(pattern_id: UUID, session: SessionDep) -> ApiResponse[PatternRead]:
    """Fetch one saved pattern by identifier."""

    return success_response(StudioService(session).get_pattern(str(pattern_id)))


@router.patch("/patterns/{pattern_id}", response_model=ApiResponse[PatternRead])
def update_pattern(
    pattern_id: UUID,
    payload: PatternUpdate,
    session: SessionDep,
) -> ApiResponse[PatternRead]:
    """Update part of a saved pattern without replacing the whole record."""

    return success_response(StudioService(session).update_pattern(str(pattern_id), payload))


@router.post("/patterns/from-selection", response_model=ApiResponse[PatternRead], status_code=201)
def create_pattern_from_selection(
    payload: PatternFromSelectionRequest,
    session: SessionDep,
) -> ApiResponse[PatternRead]:
    """Create an exact-value pattern directly from a selected value."""

    return success_response(StudioService(session).create_pattern_from_selection(payload))


@router.post("/entities", response_model=ApiResponse[CustomEntityRead], status_code=201)
def create_custom_entity(
    payload: CustomEntityCreate,
    session: SessionDep,
) -> ApiResponse[CustomEntityRead]:
    """Create a reusable custom entity with one or more detection definitions."""

    return success_response(StudioService(session).create_custom_entity(payload))


@router.get("/entities", response_model=ApiResponse[list[CustomEntityRead]])
def list_custom_entities(
    session: SessionDep,
    pagination: PaginationDep,
) -> ApiResponse[list[CustomEntityRead]]:
    """List saved custom entities."""

    items, pagination_meta = StudioService(session).list_custom_entities(pagination)
    return success_response(items, pagination=pagination_meta)


@router.get("/entities/{entity_id}", response_model=ApiResponse[CustomEntityRead])
def get_custom_entity(entity_id: UUID, session: SessionDep) -> ApiResponse[CustomEntityRead]:
    """Fetch one saved custom entity by identifier."""

    return success_response(StudioService(session).get_custom_entity(str(entity_id)))


@router.patch("/entities/{entity_id}", response_model=ApiResponse[CustomEntityRead])
def update_custom_entity(
    entity_id: UUID,
    payload: CustomEntityUpdate,
    session: SessionDep,
) -> ApiResponse[CustomEntityRead]:
    """Update part of a saved custom entity."""

    return success_response(StudioService(session).update_custom_entity(str(entity_id), payload))


@router.post("/configurations", response_model=ApiResponse[ConfigurationRead], status_code=201)
def create_configuration(
    payload: ConfigurationCreate,
    session: SessionDep,
) -> ApiResponse[ConfigurationRead]:
    """Create a reusable pack, profile, or preset."""

    return success_response(StudioService(session).create_configuration(payload))


@router.get("/configurations", response_model=ApiResponse[list[ConfigurationRead]])
def list_configurations(
    session: SessionDep,
    pagination: PaginationDep,
) -> ApiResponse[list[ConfigurationRead]]:
    """List saved packs, profiles, and presets."""

    items, pagination_meta = StudioService(session).list_configurations(pagination)
    return success_response(items, pagination=pagination_meta)


@router.get("/configurations/{configuration_id}", response_model=ApiResponse[ConfigurationRead])
def get_configuration(
    configuration_id: UUID, session: SessionDep
) -> ApiResponse[ConfigurationRead]:
    """Fetch one saved configuration asset by identifier."""

    return success_response(StudioService(session).get_configuration(str(configuration_id)))


@router.patch("/configurations/{configuration_id}", response_model=ApiResponse[ConfigurationRead])
def update_configuration(
    configuration_id: UUID,
    payload: ConfigurationUpdate,
    session: SessionDep,
) -> ApiResponse[ConfigurationRead]:
    """Update part of a saved configuration asset."""

    return success_response(
        StudioService(session).update_configuration(str(configuration_id), payload)
    )


@router.get("/search", response_model=ApiResponse[list[SearchResultItem]])
def search_studio(
    session: SessionDep,
    pagination: PaginationDep,
    q: str = Query(..., min_length=1),
) -> ApiResponse[list[SearchResultItem]]:
    """Search across saved studio assets and persisted jobs."""

    items, pagination_meta = SearchService(session).search(q.strip(), pagination)
    return success_response(items, pagination=pagination_meta)
