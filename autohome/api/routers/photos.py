"""Маршруты фотографий и цветов галереи серий."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.errors import not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import GalleryColorsResponse, PhotoPage
from autohome.models import (
    Series,
    SeriesGalleryColor,
    SeriesPhoto,
    SeriesPhotoColor,
)


def create_photos_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер фотографий серий."""
    router = APIRouter(
        tags=["Series"],
        dependencies=[Depends(require_authenticated_user)],
    )

    @router.get(
        "/api/v1/series/{series_id}/photos",
        response_model=PhotoPage,
        summary="Получить фотографии серии",
    )
    async def photos(
        series_id: int = ApiPath(description="Идентификатор серии."),
        spec_id: int | None = Query(
            None, description="Оставить фотографии указанной комплектации."
        ),
        category_id: int | None = Query(
            None, description="Оставить фотографии указанной категории."
        ),
        color_scope: str | None = Query(
            None, description="Область цвета: EXTERIOR или INTERIOR."
        ),
        color_id: int | None = Query(None, description="Идентификатор цвета."),
        limit: int = Query(
            24,
            ge=1,
            le=100,
            description="Максимальное число элементов на странице.",
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Series, series_id) is None:
            raise not_found("Series")
        statement = select(SeriesPhoto).where(SeriesPhoto.series_id == series_id)
        if spec_id is not None:
            statement = statement.where(SeriesPhoto.spec_id == spec_id)
        if category_id is not None:
            statement = statement.where(SeriesPhoto.category_id == category_id)
        if color_scope is not None or color_id is not None:
            color_match = select(SeriesPhotoColor.photo_id).where(
                SeriesPhotoColor.photo_id == SeriesPhoto.id
            )
            if color_scope is not None:
                color_match = color_match.where(
                    func.lower(SeriesPhotoColor.color_scope) == color_scope.lower()
                )
            if color_id is not None:
                color_match = color_match.where(SeriesPhotoColor.color_id == color_id)
            statement = statement.where(exists(color_match))
        statement = statement.order_by(SeriesPhoto.id)
        rows, pagination = await page(session, statement, limit, offset, include_total)
        photos_list = [row[0] for row in rows]
        ids = [photo.id for photo in photos_list]
        color_rows = (
            (
                await session.execute(
                    select(SeriesPhotoColor, SeriesGalleryColor)
                    .join(
                        SeriesGalleryColor,
                        and_(
                            SeriesGalleryColor.series_id == SeriesPhotoColor.series_id,
                            SeriesGalleryColor.color_scope
                            == SeriesPhotoColor.color_scope,
                            SeriesGalleryColor.color_id == SeriesPhotoColor.color_id,
                        ),
                    )
                    .where(SeriesPhotoColor.photo_id.in_(ids))
                )
            ).all()
            if ids
            else []
        )
        by_photo: dict[int, list] = {}
        for link, color in color_rows:
            by_photo.setdefault(link.photo_id, []).append(
                {
                    "color_scope": color.color_scope.upper(),
                    "color_id": color.color_id,
                    "name": color.name,
                    "color_values": color.color_values,
                    "picture_count": color.picture_count,
                    "gallery_url": color.gallery_url,
                }
            )
        items = [
            {
                "id": photo.id,
                "series_id": photo.series_id,
                "spec_id": photo.spec_id,
                "category_id": photo.category_id,
                "category_name": photo.category_name,
                "title": photo.title,
                "image_url": photo.image_url,
                "thumbnail_url": photo.thumbnail_url,
                "colors": by_photo.get(photo.id, []),
            }
            for photo in photos_list
        ]
        return {"items": items, "pagination": pagination}

    @router.get(
        "/api/v1/series/{series_id}/gallery-colors",
        response_model=GalleryColorsResponse,
        summary="Получить цвета галереи",
    )
    async def gallery_colors(
        series_id: int = ApiPath(description="Идентификатор серии."),
        color_scope: str | None = Query(
            None, description="Область цвета: EXTERIOR или INTERIOR."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Series, series_id) is None:
            raise not_found("Series")
        statement = select(SeriesGalleryColor).where(
            SeriesGalleryColor.series_id == series_id
        )
        if color_scope is not None:
            statement = statement.where(
                func.lower(SeriesGalleryColor.color_scope) == color_scope.lower()
            )
        values = await session.execute(
            statement.order_by(
                SeriesGalleryColor.color_scope,
                SeriesGalleryColor.name,
            )
        )
        return {
            "items": [
                {
                    "series_id": item.series_id,
                    "color_scope": item.color_scope.upper(),
                    "color_id": item.color_id,
                    "name": item.name,
                    "color_values": item.color_values,
                    "picture_count": item.picture_count,
                    "gallery_url": item.gallery_url,
                }
                for item in values.scalars()
            ]
        }

    return router
