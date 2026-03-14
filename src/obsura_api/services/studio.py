"""CRUD services for persistent studio assets."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from obsura_api.db.models import CustomEntity, Pattern, StudioConfiguration
from obsura_api.domain.common import PaginationMeta, PaginationParams, build_pagination_meta
from obsura_api.domain.enums import MatcherKind
from obsura_api.domain.studio import (
    ConfigurationCreate,
    ConfigurationRead,
    ConfigurationUpdate,
    CustomEntityCreate,
    CustomEntityRead,
    CustomEntityUpdate,
    PatternCreate,
    PatternFromSelectionRequest,
    PatternMatcherDefinition,
    PatternRead,
    PatternUpdate,
)


class StudioService:
    """Manage saved patterns, entities, and configurations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_pattern(self, payload: PatternCreate) -> PatternRead:
        pattern = Pattern(**payload.model_dump())
        self.session.add(pattern)
        self.session.commit()
        self.session.refresh(pattern)
        return PatternRead.model_validate(pattern, from_attributes=True)

    def list_patterns(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[PatternRead], PaginationMeta]:
        total_items = self.session.scalar(select(func.count()).select_from(Pattern)) or 0
        patterns = self.session.scalars(
            select(Pattern)
            .order_by(Pattern.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size),
        ).all()
        return (
            [PatternRead.model_validate(item, from_attributes=True) for item in patterns],
            build_pagination_meta(params=pagination, total_items=total_items),
        )

    def get_pattern(self, pattern_id: str) -> PatternRead:
        pattern = self.session.get(Pattern, pattern_id)
        if pattern is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pattern not found")
        return PatternRead.model_validate(pattern, from_attributes=True)

    def update_pattern(self, pattern_id: str, payload: PatternUpdate) -> PatternRead:
        pattern = self.session.get(Pattern, pattern_id)
        if pattern is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pattern not found")
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(pattern, field_name, value)
        self.session.commit()
        self.session.refresh(pattern)
        return PatternRead.model_validate(pattern, from_attributes=True)

    def create_pattern_from_selection(self, payload: PatternFromSelectionRequest) -> PatternRead:
        pattern = PatternCreate(
            name=payload.name,
            description=payload.description,
            category=payload.category,
            tags=payload.tags,
            matcher=PatternMatcherDefinition(
                kind=MatcherKind.EXACT,
                value=payload.selected_value,
                applies_to=payload.applies_to,
            ),
            transformation=payload.transformation,
        )
        return self.create_pattern(pattern)

    def create_custom_entity(self, payload: CustomEntityCreate) -> CustomEntityRead:
        entity = CustomEntity(**payload.model_dump())
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return CustomEntityRead.model_validate(entity, from_attributes=True)

    def list_custom_entities(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[CustomEntityRead], PaginationMeta]:
        total_items = self.session.scalar(select(func.count()).select_from(CustomEntity)) or 0
        entities = self.session.scalars(
            select(CustomEntity)
            .order_by(CustomEntity.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size),
        ).all()
        return (
            [CustomEntityRead.model_validate(item, from_attributes=True) for item in entities],
            build_pagination_meta(params=pagination, total_items=total_items),
        )

    def get_custom_entity(self, entity_id: str) -> CustomEntityRead:
        entity = self.session.get(CustomEntity, entity_id)
        if entity is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Custom entity not found")
        return CustomEntityRead.model_validate(entity, from_attributes=True)

    def update_custom_entity(
        self,
        entity_id: str,
        payload: CustomEntityUpdate,
    ) -> CustomEntityRead:
        entity = self.session.get(CustomEntity, entity_id)
        if entity is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Custom entity not found")
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(entity, field_name, value)
        self.session.commit()
        self.session.refresh(entity)
        return CustomEntityRead.model_validate(entity, from_attributes=True)

    def create_configuration(self, payload: ConfigurationCreate) -> ConfigurationRead:
        self._validate_configuration_references(
            pattern_ids=payload.pattern_ids,
            custom_entity_ids=payload.custom_entity_ids,
        )
        data = payload.model_dump()
        extra_data = dict(data["metadata"])
        if data.get("pii_detection") is not None:
            extra_data["pii_detection"] = data["pii_detection"]
        configuration = StudioConfiguration(
            **{
                key: value
                for key, value in data.items()
                if key not in {"metadata", "pii_detection"}
            },
            extra_data=extra_data,
        )
        self.session.add(configuration)
        self.session.commit()
        self.session.refresh(configuration)
        return self._configuration_to_schema(configuration)

    def list_configurations(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[ConfigurationRead], PaginationMeta]:
        total_items = (
            self.session.scalar(select(func.count()).select_from(StudioConfiguration)) or 0
        )
        configurations = self.session.scalars(
            select(StudioConfiguration)
            .order_by(StudioConfiguration.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size),
        ).all()
        return (
            [self._configuration_to_schema(item) for item in configurations],
            build_pagination_meta(params=pagination, total_items=total_items),
        )

    def get_configuration(self, configuration_id: str) -> ConfigurationRead:
        configuration = self.session.get(StudioConfiguration, configuration_id)
        if configuration is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Configuration not found")
        return self._configuration_to_schema(configuration)

    def update_configuration(
        self,
        configuration_id: str,
        payload: ConfigurationUpdate,
    ) -> ConfigurationRead:
        configuration = self.session.get(StudioConfiguration, configuration_id)
        if configuration is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Configuration not found")
        updates = payload.model_dump(exclude_unset=True)
        self._validate_configuration_references(
            pattern_ids=updates.get("pattern_ids", configuration.pattern_ids),
            custom_entity_ids=updates.get("custom_entity_ids", configuration.custom_entity_ids),
        )
        for field_name, value in updates.items():
            if field_name == "metadata":
                existing_pii_detection = configuration.extra_data.get("pii_detection")
                configuration.extra_data = dict(value)
                if existing_pii_detection is not None:
                    configuration.extra_data["pii_detection"] = existing_pii_detection
            elif field_name == "pii_detection":
                configuration.extra_data = dict(configuration.extra_data)
                if value is None:
                    configuration.extra_data.pop("pii_detection", None)
                else:
                    configuration.extra_data["pii_detection"] = value
            else:
                setattr(configuration, field_name, value)
        self.session.commit()
        self.session.refresh(configuration)
        return self._configuration_to_schema(configuration)

    def resolve_patterns(self, pattern_ids: list[str]) -> list[Pattern]:
        if not pattern_ids:
            return []
        rows = self.session.scalars(select(Pattern).where(Pattern.id.in_(pattern_ids))).all()
        return self._ordered_entities(pattern_ids, rows, "Pattern")

    def resolve_custom_entities(self, entity_ids: list[str]) -> list[CustomEntity]:
        if not entity_ids:
            return []
        rows = self.session.scalars(
            select(CustomEntity).where(CustomEntity.id.in_(entity_ids)),
        ).all()
        return self._ordered_entities(entity_ids, rows, "Custom entity")

    def resolve_configurations(self, configuration_ids: list[str]) -> list[StudioConfiguration]:
        if not configuration_ids:
            return []
        rows = self.session.scalars(
            select(StudioConfiguration).where(StudioConfiguration.id.in_(configuration_ids)),
        ).all()
        return self._ordered_entities(configuration_ids, rows, "Configuration")

    def _configuration_to_schema(self, configuration: StudioConfiguration) -> ConfigurationRead:
        metadata = dict(configuration.extra_data)
        pii_detection = metadata.pop("pii_detection", None)
        return ConfigurationRead(
            id=configuration.id,
            created_at=configuration.created_at,
            updated_at=configuration.updated_at,
            kind=configuration.kind,
            name=configuration.name,
            description=configuration.description,
            category=configuration.category,
            tags=configuration.tags,
            is_active=configuration.is_active,
            pattern_ids=configuration.pattern_ids,
            custom_entity_ids=configuration.custom_entity_ids,
            default_text_transformation=configuration.default_text_transformation,
            default_image_transformation=configuration.default_image_transformation,
            pii_detection=pii_detection,
            face_preferences=configuration.face_preferences,
            metadata=metadata,
        )

    def _validate_configuration_references(
        self,
        *,
        pattern_ids: list[str],
        custom_entity_ids: list[str],
    ) -> None:
        self.resolve_patterns(pattern_ids)
        self.resolve_custom_entities(custom_entity_ids)

    def _ordered_entities(
        self,
        expected_ids: list[str],
        rows: list[object],
        entity_label: str,
    ) -> list[object]:
        by_id = {getattr(row, "id"): row for row in rows}
        missing_ids = [item_id for item_id in expected_ids if item_id not in by_id]
        if missing_ids:
            missing_label = ", ".join(missing_ids)
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"{entity_label} reference not found: {missing_label}",
            )
        return [by_id[item_id] for item_id in expected_ids]
