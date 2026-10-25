"""Маршруты технических модификаций автомобилей."""

from collections.abc import Callable
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.common import (
    PRICE_FROM_DESCRIPTION,
    PRICE_TO_DESCRIPTION,
    PRICE_TYPE_DESCRIPTION,
    PriceType,
    SortOrder,
    decimal_value,
    effective_price,
    money,
    price_column,
)
from autohome.api.errors import check_range, not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import ModificationPage, ModificationResponse
from autohome.models import Modification, Series, Spec


def create_modifications_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер технических модификаций."""
    router = APIRouter(
        tags=["Modifications"],
        dependencies=[Depends(require_authenticated_user)],
    )

    async def modification_list_impl(
        session: AsyncSession,
        *,
        series_id=None,
        brand_id=None,
        year_from=None,
        year_to=None,
        energy_type=None,
        body_type=None,
        drive_type=None,
        transmission_type=None,
        engine_displacement_from=None,
        engine_displacement_to=None,
        power_hp_from=None,
        power_hp_to=None,
        price_from=None,
        price_to=None,
        price_type="effective",
        sort="year",
        order="desc",
        limit=24,
        offset=0,
        include_total=False,
    ):
        for low, high, name in (
            (year_from, year_to, "year"),
            (
                engine_displacement_from,
                engine_displacement_to,
                "engine_displacement",
            ),
            (power_hp_from, power_hp_to, "power_hp"),
            (price_from, price_to, "price"),
        ):
            check_range(low, high, name)
        selected_price = price_column(price_type)
        prices = (
            select(
                Spec.modification_id,
                func.min(selected_price).label("min_price"),
                func.max(selected_price).label("max_price"),
            )
            .group_by(Spec.modification_id)
            .subquery()
        )
        statement = select(
            Modification, prices.c.min_price, prices.c.max_price
        ).outerjoin(prices, prices.c.modification_id == Modification.id)
        filters = []
        mappings = (
            (Modification.series_id, series_id),
            (Modification.energy_type, energy_type),
            (Modification.body_type, body_type),
            (Modification.drive_type, drive_type),
            (Modification.transmission_type, transmission_type),
        )
        filters.extend(
            column == value for column, value in mappings if value is not None
        )
        if brand_id is not None:
            filters.append(
                exists(
                    select(Series.id).where(
                        Series.id == Modification.series_id,
                        Series.brand_id == brand_id,
                    )
                )
            )
        for column, low, high in (
            (Modification.model_year, year_from, year_to),
            (
                Modification.engine_displacement_ml,
                engine_displacement_from,
                engine_displacement_to,
            ),
            (Modification.engine_power_hp, power_hp_from, power_hp_to),
            (prices.c.min_price, price_from, price_to),
        ):
            if low is not None:
                filters.append(column >= low)
            if high is not None:
                filters.append(column <= high)
        sort_column = {
            "year": Modification.model_year,
            "power": Modification.engine_power_hp,
            "engine_displacement": Modification.engine_displacement_ml,
            "price": prices.c.min_price,
            "name": Modification.name,
        }[sort]
        statement = statement.where(*filters).order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(),
            Modification.id.asc(),
        )
        rows, pagination = await page(session, statement, limit, offset, include_total)
        items = [
            {
                "id": item.id,
                "series_id": item.series_id,
                "model_year": item.model_year,
                "name": item.name,
                "energy_type": item.energy_type,
                "engine_summary": item.engine_summary,
                "engine_displacement_ml": item.engine_displacement_ml,
                "engine_power_kw": decimal_value(item.engine_power_kw),
                "engine_power_hp": decimal_value(item.engine_power_hp),
                "transmission_summary": item.transmission_summary,
                "transmission_type": item.transmission_type,
                "drive_type": item.drive_type,
                "body_type": item.body_type,
                "battery_capacity_kwh": decimal_value(item.battery_capacity_kwh),
                "spec_count": item.spec_count,
                "price": {"min_cny": money(minimum), "max_cny": money(maximum)},
            }
            for item, minimum, maximum in rows
        ]
        return {"items": items, "pagination": pagination}

    @router.get(
        "/api/v1/modifications",
        response_model=ModificationPage,
        summary="Получить модификации",
    )
    async def modifications(
        series_id: int | None = Query(None, description="Идентификатор серии."),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        year_from: int | None = Query(None, description="Минимальный модельный год."),
        year_to: int | None = Query(None, description="Максимальный модельный год."),
        energy_type: str | None = Query(
            None, description="Нормализованный код типа энергии."
        ),
        body_type: str | None = Query(
            None, description="Нормализованный код типа кузова."
        ),
        drive_type: str | None = Query(
            None, description="Нормализованный код типа привода."
        ),
        transmission_type: str | None = Query(
            None, description="Нормализованный код типа трансмиссии."
        ),
        engine_displacement_from: int | None = Query(
            None, description="Минимальный рабочий объём ДВС в миллилитрах."
        ),
        engine_displacement_to: int | None = Query(
            None, description="Максимальный рабочий объём ДВС в миллилитрах."
        ),
        power_hp_from: Decimal | None = Query(
            None, description="Минимальная мощность ДВС в лошадиных силах."
        ),
        power_hp_to: Decimal | None = Query(
            None, description="Максимальная мощность ДВС в лошадиных силах."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
        sort: Literal["year", "power", "engine_displacement", "price", "name"] = Query(
            "year", description="Поле сортировки."
        ),
        order: SortOrder = Query(
            "desc", description="Направление сортировки: asc или desc."
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
        argument_names = {
            "series_id",
            "brand_id",
            "year_from",
            "year_to",
            "energy_type",
            "body_type",
            "drive_type",
            "transmission_type",
            "engine_displacement_from",
            "engine_displacement_to",
            "power_hp_from",
            "power_hp_to",
            "price_from",
            "price_to",
            "price_type",
            "sort",
            "order",
            "limit",
            "offset",
            "include_total",
        }
        return await modification_list_impl(
            session,
            **{key: value for key, value in locals().items() if key in argument_names},
        )

    @router.get(
        "/api/v1/series/{series_id}/modifications",
        response_model=ModificationPage,
        summary="Получить модификации серии",
    )
    async def series_modifications(
        series_id: int = ApiPath(description="Идентификатор серии."),
        year_from: int | None = Query(None, description="Минимальный модельный год."),
        year_to: int | None = Query(None, description="Максимальный модельный год."),
        energy_type: str | None = Query(
            None, description="Нормализованный код типа энергии."
        ),
        body_type: str | None = Query(
            None, description="Нормализованный код типа кузова."
        ),
        drive_type: str | None = Query(
            None, description="Нормализованный код типа привода."
        ),
        transmission_type: str | None = Query(
            None, description="Нормализованный код типа трансмиссии."
        ),
        engine_displacement_from: int | None = Query(
            None, description="Минимальный рабочий объём ДВС в миллилитрах."
        ),
        engine_displacement_to: int | None = Query(
            None, description="Максимальный рабочий объём ДВС в миллилитрах."
        ),
        power_hp_from: Decimal | None = Query(
            None, description="Минимальная мощность ДВС в лошадиных силах."
        ),
        power_hp_to: Decimal | None = Query(
            None, description="Максимальная мощность ДВС в лошадиных силах."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
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
        return await modification_list_impl(
            session,
            series_id=series_id,
            year_from=year_from,
            year_to=year_to,
            energy_type=energy_type,
            body_type=body_type,
            drive_type=drive_type,
            transmission_type=transmission_type,
            engine_displacement_from=engine_displacement_from,
            engine_displacement_to=engine_displacement_to,
            power_hp_from=power_hp_from,
            power_hp_to=power_hp_to,
            price_from=price_from,
            price_to=price_to,
            price_type=price_type,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    @router.get(
        "/api/v1/modifications/{modification_id}",
        response_model=ModificationResponse,
        summary="Получить модификацию",
    )
    async def modification_detail(
        modification_id: int = ApiPath(
            description="Идентификатор технической модификации."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        item = await session.get(Modification, modification_id)
        if item is None:
            raise not_found("Modification")
        selected_price = effective_price()
        minimum, maximum = (
            await session.execute(
                select(func.min(selected_price), func.max(selected_price)).where(
                    Spec.modification_id == modification_id
                )
            )
        ).one()
        return {
            "id": item.id,
            "series_id": item.series_id,
            "model_year": item.model_year,
            "name": item.name,
            "energy_type": item.energy_type,
            "engine_summary": item.engine_summary,
            "engine_displacement_ml": item.engine_displacement_ml,
            "engine_power_kw": decimal_value(item.engine_power_kw),
            "engine_power_hp": decimal_value(item.engine_power_hp),
            "transmission_summary": item.transmission_summary,
            "transmission_type": item.transmission_type,
            "drive_type": item.drive_type,
            "body_type": item.body_type,
            "battery_capacity_kwh": decimal_value(item.battery_capacity_kwh),
            "spec_count": item.spec_count,
            "price": {"min_cny": money(minimum), "max_cny": money(maximum)},
        }

    return router
