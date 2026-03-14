"""Search service across saved assets and jobs."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from obsura_api.db.models import CustomEntity, Job, Pattern, StudioConfiguration
from obsura_api.domain.common import (
    PaginationMeta,
    PaginationParams,
    SearchResultItem,
    build_pagination_meta,
)
from obsura_api.domain.enums import SearchResultKind


class SearchService:
    """Search persistent saved assets and job history."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        query: str,
        pagination: PaginationParams,
    ) -> tuple[list[SearchResultItem], PaginationMeta]:
        if not query:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Search query must not be blank",
            )
        normalized = f"%{query.lower()}%"
        results: list[SearchResultItem] = []

        patterns = self.session.scalars(
            select(Pattern).where(
                func.lower(Pattern.name).like(normalized)
                | func.lower(func.coalesce(Pattern.description, "")).like(normalized),
            ),
        ).all()
        results.extend(
            SearchResultItem(
                kind=SearchResultKind.PATTERN,
                id=item.id,
                name=item.name,
                description=item.description,
                category=item.category,
                tags=item.tags,
            )
            for item in patterns
        )

        entities = self.session.scalars(
            select(CustomEntity).where(
                func.lower(CustomEntity.name).like(normalized)
                | func.lower(func.coalesce(CustomEntity.description, "")).like(normalized),
            ),
        ).all()
        results.extend(
            SearchResultItem(
                kind=SearchResultKind.CUSTOM_ENTITY,
                id=item.id,
                name=item.name,
                description=item.description,
                category=item.category,
                tags=item.tags,
            )
            for item in entities
        )

        configurations = self.session.scalars(
            select(StudioConfiguration).where(
                func.lower(StudioConfiguration.name).like(normalized)
                | func.lower(func.coalesce(StudioConfiguration.description, "")).like(normalized),
            ),
        ).all()
        results.extend(
            SearchResultItem(
                kind=SearchResultKind.CONFIGURATION,
                id=item.id,
                name=item.name,
                description=item.description,
                category=item.category,
                tags=item.tags,
            )
            for item in configurations
        )

        jobs = self.session.scalars(
            select(Job).where(func.lower(func.coalesce(Job.title, "")).like(normalized)),
        ).all()
        results.extend(
            SearchResultItem(
                kind=SearchResultKind.JOB,
                id=item.id,
                name=item.title or item.id,
                description=f"{item.content_type.value} job",
                category="job",
                tags=[],
            )
            for item in jobs
        )

        results.sort(key=lambda item: (item.kind.value, item.name.lower(), item.id))
        total_items = len(results)
        paged_results = results[pagination.offset : pagination.offset + pagination.page_size]
        return paged_results, build_pagination_meta(params=pagination, total_items=total_items)
