"""Общие запросы, фильтры и преобразования данных каталога API."""

from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import case, func, or_, select

from autohome.api.schemas import SeriesState
from autohome.models import (
    Brand,
    Manufacturer,
    Modification,
    Series,
    Spec,
    SpecPowertrain,
    SpecVehicleAttributes,
)

PriceType = Literal["effective", "guide", "dealer"]
SortOrder = Literal["asc", "desc"]
SERIES_STATE_CODES = {
    SeriesState.UPCOMING: (10,),
    SeriesState.CURRENT: (20, 30),
    SeriesState.DISCONTINUED: (0, 40),
}
KNOWN_SERIES_STATE_CODES = tuple(
    code for codes in SERIES_STATE_CODES.values() for code in codes
)
SPEC_STATE_CODES = {
    SeriesState.UPCOMING: (0, 10),
    SeriesState.CURRENT: (20, 30),
    SeriesState.DISCONTINUED: (40,),
}
KNOWN_SPEC_STATE_CODES = tuple(
    code for codes in SPEC_STATE_CODES.values() for code in codes
)
PRICE_FROM_DESCRIPTION = (
    "Минимальная цена в CNY. Тип цены задаётся параметром price_type. "
    "Записи без цены выбранного типа не возвращаются."
)
PRICE_TO_DESCRIPTION = (
    "Максимальная цена в CNY. Тип цены задаётся параметром price_type. "
    "Записи без цены выбранного типа не возвращаются."
)
PRICE_TYPE_DESCRIPTION = (
    "Тип цены: effective — рекомендованная или дилерская при её отсутствии; "
    "guide — рекомендованная; dealer — дилерская."
)
EXPECTED_CUSTOMS_PAYMENT_TYPES = {
    "IMPORT_DUTY",
    "CUSTOMS_FEE",
    "RECYCLING_FEE",
    "EXCISE",
    "VAT",
}
LEGACY_CUSTOMS_PAYMENT_TYPE_SETS = {
    frozenset(EXPECTED_CUSTOMS_PAYMENT_TYPES - {"VAT"}),
    frozenset(EXPECTED_CUSTOMS_PAYMENT_TYPES - {"VAT", "EXCISE"}),
}


def money(value: Decimal | None) -> str | None:
    """Представить денежное значение с двумя знаками после запятой."""
    return format(value, ".2f") if value is not None else None


def decimal_value(value: Decimal | None) -> str | None:
    """Представить Decimal строкой без экспоненциальной записи."""
    return format(value, "f") if value is not None else None


def series_state(value: int | None) -> SeriesState:
    """Преобразовать исходный код Autohome в публичную стадию продаж."""
    for state, codes in SERIES_STATE_CODES.items():
        if value in codes:
            return state
    return SeriesState.UNKNOWN


def spec_state(value: int | None) -> SeriesState:
    """Преобразовать исходный код комплектации в публичную стадию продаж."""
    for state, codes in SPEC_STATE_CODES.items():
        if value in codes:
            return state
    return SeriesState.UNKNOWN


def public_payment_details(details: dict[str, Any]) -> dict[str, Any]:
    """Исключить устаревшие интерфейсные подписи из деталей платежа."""
    return {key: value for key, value in details.items() if key != "field_labels"}


def effective_price():
    """Сформировать SQL-выражение эффективной цены комплектации."""
    return case(
        (Spec.guide_price_yuan > 0, Spec.guide_price_yuan),
        (Spec.dealer_price_yuan > 0, Spec.dealer_price_yuan),
        else_=None,
    )


def price_column(price_type: PriceType):
    """Получить SQL-выражение выбранного типа цены."""
    return {
        "effective": effective_price(),
        "guide": Spec.guide_price_yuan,
        "dealer": Spec.dealer_price_yuan,
    }[price_type]


def contains_pattern(value: str) -> str:
    """Экранировать пользовательский текст для поиска через SQL LIKE."""
    escaped = value.lower().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def brand_ref(brand: Brand | None):
    """Сформировать краткую ссылку на бренд."""
    return {"id": brand.id, "name": brand.name} if brand else None


def series_ref(series: Series | None):
    """Сформировать краткую ссылку на серию."""
    return {"id": series.id, "name": series.name} if series else None


def manufacturer_ref(manufacturer: Manufacturer | None):
    """Сформировать краткую ссылку на производителя."""
    return {"id": manufacturer.id, "name": manufacturer.name} if manufacturer else None


def price_payload(spec: Spec):
    """Сформировать публичное представление цен комплектации."""
    if spec.guide_price_yuan is not None and spec.guide_price_yuan > 0:
        effective, source = spec.guide_price_yuan, "GUIDE"
    elif spec.dealer_price_yuan is not None and spec.dealer_price_yuan > 0:
        effective, source = spec.dealer_price_yuan, "DEALER"
    else:
        effective, source = None, "MISSING"
    return {
        "guide_cny": money(spec.guide_price_yuan),
        "dealer_cny": money(spec.dealer_price_yuan),
        "discount_cny": money(spec.discount_yuan),
        "effective_cny": money(effective),
        "source": source,
    }


def powertrain_payload(item: SpecPowertrain | None):
    """Сформировать публичное представление силовой установки."""
    if item is None:
        return None
    return {
        "energy_type": item.energy_type,
        "engine_summary": item.engine_summary,
        "engine_displacement_ml": item.engine_displacement_ml,
        "engine_power_kw": decimal_value(item.engine_power_kw),
        "engine_power_hp": decimal_value(item.engine_power_hp),
        "maximum_power_kw": decimal_value(item.maximum_power_kw),
        "transmission_summary": item.transmission_summary,
        "transmission_type": item.transmission_type,
        "drive_type": item.drive_type,
        "motor_total_power_kw": decimal_value(item.motor_total_power_kw),
        "motor_total_power_hp": decimal_value(item.motor_total_power_hp),
        "battery_capacity_kwh": decimal_value(item.battery_capacity_kwh),
        "battery_type": item.battery_type,
    }


def attributes_payload(item: SpecVehicleAttributes | None):
    """Сформировать публичное представление атрибутов автомобиля."""
    if item is None:
        return None
    fields = (
        "vehicle_class",
        "vehicle_technical_category",
        "body_type",
        "body_construction",
        "seat_count_min",
        "seat_count_max",
        "door_count",
        "curb_mass_kg",
        "gross_mass_kg",
        "length_mm",
        "width_mm",
        "height_mm",
        "wheelbase_mm",
        "is_four_wheel_drive",
    )
    return {field: getattr(item, field) for field in fields}


def spec_payload(row: Any, *, detail: bool = False):
    """Сформировать публичное представление комплектации."""
    spec, series, brand, modification, powertrain, attributes = row
    result = {
        "id": spec.id,
        "name": spec.name,
        "year": spec.year,
        "state": spec_state(spec.state),
        "brand": brand_ref(brand),
        "series": series_ref(series),
        "modification": (
            {"id": modification.id, "name": modification.name} if modification else None
        ),
        "price": price_payload(spec),
        "description": spec.description,
        "image_url": spec.image_url,
        "powertrain": powertrain_payload(powertrain),
    }
    if detail:
        result["vehicle_attributes"] = attributes_payload(attributes)
    return result


def spec_select():
    """Сформировать базовый запрос комплектаций со связанными сущностями."""
    return (
        select(Spec, Series, Brand, Modification, SpecPowertrain, SpecVehicleAttributes)
        .outerjoin(Series, Series.id == Spec.series_id)
        .outerjoin(Brand, Brand.id == Series.brand_id)
        .outerjoin(Modification, Modification.id == Spec.modification_id)
        .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
        .outerjoin(SpecVehicleAttributes, SpecVehicleAttributes.spec_id == Spec.id)
    )


def apply_spec_filters(
    statement: Any,
    *,
    q=None,
    brand_id=None,
    series_id=None,
    modification_id=None,
    manufacturer_id=None,
    year_from=None,
    year_to=None,
    state=None,
    energy_type=None,
    body_type=None,
    drive_type=None,
    transmission_type=None,
    engine_displacement_from=None,
    engine_displacement_to=None,
    power_hp_from=None,
    power_hp_to=None,
    seats_from=None,
    seats_to=None,
    four_wheel_drive=None,
    price_from=None,
    price_to=None,
    price_type="effective",
):
    """Применить общие фильтры каталога к запросу комплектаций."""
    filters = []
    if q:
        filters.append(func.lower(Spec.name).like(contains_pattern(q), escape="\\"))
    mappings = (
        (Series.brand_id, brand_id),
        (Spec.series_id, series_id),
        (Spec.modification_id, modification_id),
        (Series.manufacturer_id, manufacturer_id),
        (SpecPowertrain.energy_type, energy_type),
        (SpecPowertrain.body_type, body_type),
        (SpecPowertrain.drive_type, drive_type),
        (SpecPowertrain.transmission_type, transmission_type),
        (SpecVehicleAttributes.is_four_wheel_drive, four_wheel_drive),
    )
    filters.extend(column == value for column, value in mappings if value is not None)
    if state == SeriesState.UNKNOWN:
        filters.append(
            or_(Spec.state.is_(None), Spec.state.not_in(KNOWN_SPEC_STATE_CODES))
        )
    elif state is not None:
        filters.append(Spec.state.in_(SPEC_STATE_CODES[state]))
    ranges = (
        (Spec.year, year_from, year_to),
        (
            SpecPowertrain.engine_displacement_ml,
            engine_displacement_from,
            engine_displacement_to,
        ),
        (SpecPowertrain.engine_power_hp, power_hp_from, power_hp_to),
        (SpecVehicleAttributes.seat_count_max, seats_from, seats_to),
        (price_column(price_type), price_from, price_to),
    )
    for column, minimum, maximum in ranges:
        if minimum is not None:
            filters.append(column >= minimum)
        if maximum is not None:
            filters.append(column <= maximum)
    return statement.where(*filters)
