"""Маршруты комплектаций и их характеристик."""

from collections.abc import Callable
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.common import (
    PRICE_FROM_DESCRIPTION,
    PRICE_TO_DESCRIPTION,
    PRICE_TYPE_DESCRIPTION,
    PriceType,
    SortOrder,
    apply_spec_filters,
    money,
    price_column,
    spec_payload,
    spec_select,
)
from autohome.api.errors import check_range, not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import (
    ParameterGroupsResponse,
    SeriesState,
    SpecDetailResponse,
    SpecPage,
)
from autohome.models import (
    Modification,
    ParameterDefinition,
    ParameterGroup,
    ParameterSection,
    ParameterSubitem,
    Spec,
    SpecParameter,
    SpecPowertrain,
)


def create_specs_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер комплектаций."""
    router = APIRouter(
        tags=["Specs"],
        dependencies=[Depends(require_authenticated_user)],
    )

    async def specs_impl(
        session: AsyncSession,
        limit: int,
        offset: int,
        include_total: bool,
        sort="price",
        order="asc",
        **filters,
    ):
        ranges = (
            (filters.get("year_from"), filters.get("year_to"), "year"),
            (
                filters.get("engine_displacement_from"),
                filters.get("engine_displacement_to"),
                "engine_displacement",
            ),
            (filters.get("power_hp_from"), filters.get("power_hp_to"), "power_hp"),
            (filters.get("seats_from"), filters.get("seats_to"), "seats"),
            (filters.get("price_from"), filters.get("price_to"), "price"),
        )
        for low, high, name in ranges:
            check_range(low, high, name)
        statement = apply_spec_filters(spec_select(), **filters)
        sort_column = {
            "price": price_column(filters.get("price_type", "effective")),
            "year": Spec.year,
            "power": SpecPowertrain.engine_power_hp,
            "engine_displacement": SpecPowertrain.engine_displacement_ml,
            "name": Spec.name,
        }[sort]
        statement = statement.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc(),
            Spec.id.asc(),
        )
        rows, pagination = await page(session, statement, limit, offset, include_total)
        return {
            "items": [spec_payload(row) for row in rows],
            "pagination": pagination,
        }

    @router.get(
        "/api/v1/specs",
        response_model=SpecPage,
        summary="Получить комплектации",
        description=(
            "Возвращает комплектации с ценами и нормализованной силовой установкой."
        ),
    )
    async def specs(
        q: str | None = Query(
            None,
            description="Поиск по части названия комплектации без учёта регистра.",
        ),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        series_id: int | None = Query(None, description="Идентификатор серии."),
        modification_id: int | None = Query(
            None, description="Идентификатор технической модификации."
        ),
        manufacturer_id: int | None = Query(
            None, description="Идентификатор производителя."
        ),
        year_from: int | None = Query(None, description="Минимальный модельный год."),
        year_to: int | None = Query(None, description="Максимальный модельный год."),
        state: SeriesState | None = Query(
            None, description="Стадия продаж комплектации."
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
        seats_from: int | None = Query(None, description="Минимальное число мест."),
        seats_to: int | None = Query(None, description="Максимальное число мест."),
        four_wheel_drive: bool | None = Query(
            None, description="Фильтр по наличию полного привода."
        ),
        price_from: Decimal | None = Query(None, description=PRICE_FROM_DESCRIPTION),
        price_to: Decimal | None = Query(None, description=PRICE_TO_DESCRIPTION),
        price_type: PriceType = Query("effective", description=PRICE_TYPE_DESCRIPTION),
        sort: Literal["price", "year", "power", "engine_displacement", "name"] = Query(
            "price", description="Поле сортировки."
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
        filter_names = {
            "q",
            "brand_id",
            "series_id",
            "modification_id",
            "manufacturer_id",
            "year_from",
            "year_to",
            "state",
            "energy_type",
            "body_type",
            "drive_type",
            "transmission_type",
            "engine_displacement_from",
            "engine_displacement_to",
            "power_hp_from",
            "power_hp_to",
            "seats_from",
            "seats_to",
            "four_wheel_drive",
            "price_from",
            "price_to",
            "price_type",
        }
        values = {key: value for key, value in locals().items() if key in filter_names}
        return await specs_impl(
            session, limit, offset, include_total, sort=sort, order=order, **values
        )

    @router.get(
        "/api/v1/modifications/{modification_id}/specs",
        response_model=SpecPage,
        summary="Получить комплектации модификации",
    )
    async def modification_specs(
        modification_id: int = ApiPath(
            description="Идентификатор технической модификации."
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
        if await session.get(Modification, modification_id) is None:
            raise not_found("Modification")
        return await specs_impl(
            session,
            limit,
            offset,
            include_total,
            modification_id=modification_id,
            price_from=price_from,
            price_to=price_to,
            price_type=price_type,
        )

    @router.get(
        "/api/v1/specs/{spec_id}",
        response_model=SpecDetailResponse,
        summary="Получить комплектацию",
    )
    async def spec_detail(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        session: AsyncSession = Depends(get_session),
    ):
        row = (
            await session.execute(spec_select().where(Spec.id == spec_id))
        ).one_or_none()
        if row is None:
            raise not_found("Spec")
        return spec_payload(row, detail=True)

    @router.get(
        "/api/v1/specs/{spec_id}/parameters",
        response_model=ParameterGroupsResponse,
        summary="Получить полную конфигурацию комплектации",
    )
    async def spec_parameters(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        group_id: int | None = Query(
            None, description="Оставить указанную группу характеристик."
        ),
        section_id: int | None = Query(
            None, description="Оставить указанный раздел характеристик."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Spec, spec_id) is None:
            raise not_found("Spec")
        statement = (
            select(ParameterGroup, ParameterSection, ParameterDefinition, SpecParameter)
            .join(ParameterSection, ParameterSection.group_id == ParameterGroup.id)
            .join(
                ParameterDefinition,
                ParameterDefinition.section_id == ParameterSection.id,
            )
            .join(
                SpecParameter,
                and_(
                    SpecParameter.parameter_id == ParameterDefinition.id,
                    SpecParameter.spec_id == spec_id,
                ),
            )
            .order_by(
                ParameterGroup.position,
                ParameterSection.position,
                ParameterDefinition.id,
            )
        )
        if group_id is not None:
            statement = statement.where(ParameterGroup.id == group_id)
        if section_id is not None:
            statement = statement.where(ParameterSection.id == section_id)
        subitems = await session.execute(
            select(ParameterSubitem)
            .where(ParameterSubitem.spec_id == spec_id)
            .order_by(ParameterSubitem.parameter_id, ParameterSubitem.position)
        )
        subitems_by_parameter: dict[int, list] = {}
        for subitem in subitems.scalars():
            subitems_by_parameter.setdefault(subitem.parameter_id, []).append(
                {
                    "name": subitem.name,
                    "value": subitem.value,
                    "option_price_cny": money(subitem.option_price_yuan),
                }
            )
        groups: dict[int, dict] = {}
        sections: dict[int, dict] = {}
        result = await session.execute(statement)
        for group, section, definition, value in result:
            group_payload = groups.setdefault(
                group.id, {"id": group.id, "name": group.name, "sections": []}
            )
            section_payload = sections.get(section.id)
            if section_payload is None:
                section_payload = {
                    "id": section.id,
                    "name": section.name,
                    "parameters": [],
                }
                sections[section.id] = section_payload
                group_payload["sections"].append(section_payload)
            section_payload["parameters"].append(
                {
                    "id": definition.id,
                    "semantic_key": definition.semantic_key,
                    "name": definition.name,
                    "value": value.value,
                    "option_price_cny": money(value.option_price_yuan),
                    "video_url": value.video_url,
                    "subitems": subitems_by_parameter.get(definition.id, []),
                }
            )
        return {"items": list(groups.values())}

    return router
