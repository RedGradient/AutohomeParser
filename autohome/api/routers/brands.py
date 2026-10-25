"""Маршруты брендов автомобилей."""

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.common import SortOrder, contains_pattern
from autohome.api.errors import not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import BrandPage, BrandResponse
from autohome.models import Brand, Series


def create_brands_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер брендов."""
    router = APIRouter(
        prefix="/api/v1/brands",
        tags=["Brands"],
        dependencies=[Depends(require_authenticated_user)],
    )

    @router.get(
        "",
        response_model=BrandPage,
        summary="Получить бренды",
        description="Возвращает бренды с фильтрацией и offset-пагинацией.",
    )
    async def brands(
        q: str | None = Query(
            None, description="Поиск по части названия бренда без учёта регистра."
        ),
        manufacturer_id: int | None = Query(
            None, description="Оставить бренды указанного производителя."
        ),
        is_new_energy: bool | None = Query(
            None, description="Оставить бренды с сериями указанной категории NEV."
        ),
        sort: Literal["name", "series_count"] = Query(
            "name", description="Поле сортировки."
        ),
        order: SortOrder = Query(
            "asc", description="Направление сортировки: asc или desc."
        ),
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
        statement = select(Brand)
        matching_series = select(Series.id).where(Series.brand_id == Brand.id)
        if manufacturer_id is not None:
            matching_series = matching_series.where(
                Series.manufacturer_id == manufacturer_id
            )
        if is_new_energy is not None:
            matching_series = matching_series.where(
                Series.is_new_energy == is_new_energy
            )
        if q:
            statement = statement.where(
                func.lower(Brand.name).like(contains_pattern(q), escape="\\")
            )
        if any(value is not None for value in (manufacturer_id, is_new_energy)):
            statement = statement.where(exists(matching_series))
        sort_column = {"name": Brand.name, "series_count": Brand.series_count}[sort]
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(),
            Brand.id.asc(),
        )
        rows, pagination = await page(session, statement, limit, offset, include_total)
        items = [
            {
                "id": brand.id,
                "name": brand.name,
                "logo_url": brand.logo_url,
                "series_count": brand.series_count,
            }
            for (brand,) in rows
        ]
        return {"items": items, "pagination": pagination}

    @router.get(
        "/{brand_id}",
        response_model=BrandResponse,
        summary="Получить бренд",
    )
    async def brand_detail(
        brand_id: int = ApiPath(description="Идентификатор бренда."),
        session: AsyncSession = Depends(get_session),
    ):
        brand = await session.get(Brand, brand_id)
        if brand is None:
            raise not_found("Brand")
        return {
            "id": brand.id,
            "name": brand.name,
            "logo_url": brand.logo_url,
            "series_count": brand.series_count,
        }

    return router
