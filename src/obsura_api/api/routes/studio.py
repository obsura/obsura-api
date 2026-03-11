"""Routes for saved studio assets and search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from obsura_api.api.dependencies import get_db_session
from obsura_api.domain.common import SearchResultItem
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


@router.post("/patterns", response_model=PatternRead, status_code=201)
def create_pattern(payload: PatternCreate, session: SessionDep) -> PatternRead:
    """Create a reusable detection pattern with an optional default transformation."""

    return StudioService(session).create_pattern(payload)


@router.get("/patterns", response_model=list[PatternRead])
def list_patterns(session: SessionDep) -> list[PatternRead]:
    """List saved patterns in reverse creation order."""

    return StudioService(session).list_patterns()


@router.get("/patterns/{pattern_id}", response_model=PatternRead)
def get_pattern(pattern_id: str, session: SessionDep) -> PatternRead:
    """Fetch one saved pattern by identifier."""

    return StudioService(session).get_pattern(pattern_id)


@router.patch("/patterns/{pattern_id}", response_model=PatternRead)
def update_pattern(
    pattern_id: str,
    payload: PatternUpdate,
    session: SessionDep,
) -> PatternRead:
    """Update part of a saved pattern without replacing the whole record."""

    return StudioService(session).update_pattern(pattern_id, payload)


@router.post("/patterns/from-selection", response_model=PatternRead, status_code=201)
def create_pattern_from_selection(
    payload: PatternFromSelectionRequest,
    session: SessionDep,
) -> PatternRead:
    """Create an exact-value pattern directly from a selected value."""

    return StudioService(session).create_pattern_from_selection(payload)


@router.post("/entities", response_model=CustomEntityRead, status_code=201)
def create_custom_entity(payload: CustomEntityCreate, session: SessionDep) -> CustomEntityRead:
    """Create a reusable custom entity with one or more detection definitions."""

    return StudioService(session).create_custom_entity(payload)


@router.get("/entities", response_model=list[CustomEntityRead])
def list_custom_entities(session: SessionDep) -> list[CustomEntityRead]:
    """List saved custom entities."""

    return StudioService(session).list_custom_entities()


@router.get("/entities/{entity_id}", response_model=CustomEntityRead)
def get_custom_entity(entity_id: str, session: SessionDep) -> CustomEntityRead:
    """Fetch one saved custom entity by identifier."""

    return StudioService(session).get_custom_entity(entity_id)


@router.patch("/entities/{entity_id}", response_model=CustomEntityRead)
def update_custom_entity(
    entity_id: str,
    payload: CustomEntityUpdate,
    session: SessionDep,
) -> CustomEntityRead:
    """Update part of a saved custom entity."""

    return StudioService(session).update_custom_entity(entity_id, payload)


@router.post("/configurations", response_model=ConfigurationRead, status_code=201)
def create_configuration(
    payload: ConfigurationCreate,
    session: SessionDep,
) -> ConfigurationRead:
    """Create a reusable pack, profile, or preset."""

    return StudioService(session).create_configuration(payload)


@router.get("/configurations", response_model=list[ConfigurationRead])
def list_configurations(session: SessionDep) -> list[ConfigurationRead]:
    """List saved packs, profiles, and presets."""

    return StudioService(session).list_configurations()


@router.get("/configurations/{configuration_id}", response_model=ConfigurationRead)
def get_configuration(configuration_id: str, session: SessionDep) -> ConfigurationRead:
    """Fetch one saved configuration asset by identifier."""

    return StudioService(session).get_configuration(configuration_id)


@router.patch("/configurations/{configuration_id}", response_model=ConfigurationRead)
def update_configuration(
    configuration_id: str,
    payload: ConfigurationUpdate,
    session: SessionDep,
) -> ConfigurationRead:
    """Update part of a saved configuration asset."""

    return StudioService(session).update_configuration(configuration_id, payload)


@router.get("/search", response_model=list[SearchResultItem])
def search_studio(
    session: SessionDep,
    q: str = Query(..., min_length=1),
) -> list[SearchResultItem]:
    """Search across saved studio assets and persisted jobs."""

    return SearchService(session).search(q)
