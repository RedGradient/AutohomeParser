"""Маршруты производителей автомобилей."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.common import contains_pattern
from autohome.api.errors import not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import ManufacturerPage, ManufacturerResponse
from autohome.models import BrandManufacturer, Manufacturer


def create_manufacturers_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер производителей."""
    router = APIRouter(
        prefix="/api/v1/manufacturers",
        tags=["Manufacturers"],
        dependencies=[Depends(require_authenticated_user)],
    )

    @router.get(
        "",
        response_model=ManufacturerPage,
        summary="Получить производителей",
        description=(
            "Возвращает производителей с поиском по названию и фильтром по бренду."
        ),
    )
    async def manufacturers(
        q: str | None = Query(
            None,
            description="Поиск по части названия производителя без учёта регистра.",
        ),
        brand_id: int | None = Query(
            None, description="Оставить производителей указанного бренда."
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
        statement = select(Manufacturer)
        if brand_id is not None:
            statement = statement.join(
                BrandManufacturer,
                BrandManufacturer.manufacturer_id == Manufacturer.id,
            ).where(BrandManufacturer.brand_id == brand_id)
        if q:
            statement = statement.where(
                func.lower(Manufacturer.name).like(contains_pattern(q), escape="\\")
            )
        statement = statement.order_by(Manufacturer.name, Manufacturer.id)
        rows, pagination = await page(session, statement, limit, offset, include_total)
        return {
            "items": [{"id": item.id, "name": item.name} for (item,) in rows],
            "pagination": pagination,
        }

    @router.get(
        "/{manufacturer_id}",
        response_model=ManufacturerResponse,
        summary="Получить производителя",
    )
    async def manufacturer_detail(
        manufacturer_id: int = ApiPath(description="Идентификатор производителя."),
        session: AsyncSession = Depends(get_session),
    ):
        manufacturer = await session.get(Manufacturer, manufacturer_id)
        if manufacturer is None:
            raise not_found("Manufacturer")
        return {"id": manufacturer.id, "name": manufacturer.name}

    return router
