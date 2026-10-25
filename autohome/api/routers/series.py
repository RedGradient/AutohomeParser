"""Маршруты серий автомобилей."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.common import (
    KNOWN_SERIES_STATE_CODES,
    PRICE_FROM_DESCRIPTION,
    PRICE_TO_DESCRIPTION,
    PRICE_TYPE_DESCRIPTION,
    SERIES_STATE_CODES,
    PriceType,
    SortOrder,
    apply_spec_filters,
    brand_ref,
    contains_pattern,
    effective_price,
    manufacturer_ref,
    money,
    series_state,
)
from autohome.api.errors import check_range, not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import SeriesPage, SeriesResponse, SeriesState
from autohome.models import (
    Brand,
    Manufacturer,
    Series,
    SeriesPhoto,
    Spec,
    SpecPowertrain,
    SpecVehicleAttributes,
)


def create_series_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер серий."""
    router = APIRouter(
        prefix="/api/v1/series",
        tags=["Series"],
        dependencies=[Depends(require_authenticated_user)],
    )

    def series_statement():
        price = effective_price()
        prices = (
            select(
                Spec.series_id,
                func.min(price).label("min_price"),
                func.max(price).label("max_price"),
            )
            .group_by(Spec.series_id)
            .subquery()
        )
        return (
            select(
                Series,
                Brand,
                Manufacturer,
                prices.c.min_price,
                prices.c.max_price,
            )
            .outerjoin(Brand, Brand.id == Series.brand_id)
            .outerjoin(Manufacturer, Manufacturer.id == Series.manufacturer_id)
            .outerjoin(prices, prices.c.series_id == Series.id)
        )

    async def official_images(session: AsyncSession, series_ids: list[int]):
        if not series_ids:
            return {}
        photos = await session.execute(
            select(SeriesPhoto)
            .where(
                SeriesPhoto.series_id.in_(series_ids),
                SeriesPhoto.category_id == 53,
            )
            .order_by(SeriesPhoto.series_id, SeriesPhoto.id)
        )
        result: dict[int, list[dict[str, Any]]] = {}
        for photo in photos.scalars():
            result.setdefault(photo.series_id, []).append(
                {
                    "id": photo.id,
                    "title": photo.title,
                    "image_url": photo.image_url,
                    "thumbnail_url": photo.thumbnail_url,
                }
            )
        return result

    @router.get(
        "",
        response_model=SeriesPage,
        summary="Получить серии",
        description=(
            "Фильтрует серии по бренду, производителю и характеристикам комплектаций."
        ),
    )
    async def series_list(
        q: str | None = Query(
            None, description="Поиск по части названия серии без учёта регистра."
        ),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        manufacturer_id: int | None = Query(
            None, description="Идентификатор производителя."
        ),
        is_new_energy: bool | None = Query(
            None, description="Фильтр по принадлежности к категории NEV."
        ),
        state: SeriesState | None = Query(
            None, description="Нормализованная стадия продаж серии."
        ),
        year_from: int | None = Query(
            None, description="Минимальный модельный год комплектаций серии."
        ),
        year_to: int | None = Query(
            None, description="Максимальный модельный год комплектаций серии."
        ),
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
        sort: Literal["name", "price", "year"] = Query(
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
        statement = series_statement()
        direct = []
        for column, value in (
            (Series.brand_id, brand_id),
            (Series.manufacturer_id, manufacturer_id),
            (Series.is_new_energy, is_new_energy),
        ):
            if value is not None:
                direct.append(column == value)
        if state == SeriesState.UNKNOWN:
            direct.append(
                or_(
                    Series.state.is_(None),
                    Series.state.not_in(KNOWN_SERIES_STATE_CODES),
                )
            )
        elif state is not None:
            direct.append(Series.state.in_(SERIES_STATE_CODES[state]))
        if q:
            direct.append(
                func.lower(Series.name).like(contains_pattern(q), escape="\\")
            )
        matching_specs = apply_spec_filters(
            select(Spec.id)
            .outerjoin(Series, Series.id == Spec.series_id)
            .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
            .outerjoin(SpecVehicleAttributes, SpecVehicleAttributes.spec_id == Spec.id),
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
        ).where(Spec.series_id == Series.id)
        if any(
            value is not None
            for value in (
                year_from,
                year_to,
                energy_type,
                body_type,
                drive_type,
                transmission_type,
                engine_displacement_from,
                engine_displacement_to,
                power_hp_from,
                power_hp_to,
                price_from,
                price_to,
            )
        ):
            direct.append(exists(matching_specs))
        statement = statement.where(*direct)
        latest_year = (
            select(func.max(Spec.year))
            .where(Spec.series_id == Series.id)
            .scalar_subquery()
        )
        sort_column = {
            "name": Series.name,
            "price": statement.selected_columns.min_price,
            "year": latest_year,
        }[sort]
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(),
            Series.id.asc(),
        )
        rows, pagination = await page(session, statement, limit, offset, include_total)
        images_by_series = await official_images(session, [row[0].id for row in rows])
        items = [
            {
                "id": item.id,
                "name": item.name,
                "brand": brand_ref(brand),
                "manufacturer": manufacturer_ref(manufacturer),
                "is_new_energy": item.is_new_energy,
                "state": series_state(item.state),
                "spec_count": item.spec_count,
                "price": {"min_cny": money(minimum), "max_cny": money(maximum)},
                "official_images": images_by_series.get(item.id, []),
            }
            for item, brand, manufacturer, minimum, maximum in rows
        ]
        return {"items": items, "pagination": pagination}

    @router.get(
        "/{series_id}",
        response_model=SeriesResponse,
        summary="Получить серию",
    )
    async def series_detail(
        series_id: int = ApiPath(description="Идентификатор серии."),
        session: AsyncSession = Depends(get_session),
    ):
        row = (
            await session.execute(series_statement().where(Series.id == series_id))
        ).one_or_none()
        if row is None:
            raise not_found("Series")
        item, brand, manufacturer, minimum, maximum = row
        return {
            "id": item.id,
            "name": item.name,
            "brand": brand_ref(brand),
            "manufacturer": manufacturer_ref(manufacturer),
            "is_new_energy": item.is_new_energy,
            "state": series_state(item.state),
            "spec_count": item.spec_count,
            "price": {"min_cny": money(minimum), "max_cny": money(maximum)},
            "official_images": (await official_images(session, [item.id])).get(
                item.id, []
            ),
        }

    return router
