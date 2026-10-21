from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class RecyclingFeePowertrainType(StrEnum):
    """Нормативный тип силовой установки для расчёта утильсбора."""

    ICE = "ICE"
    HEV = "HEV"
    PHEV = "PHEV"
    SERIES_HEV = "SERIES_HEV"
    EREV = "EREV"
    EV = "EV"
    UNKNOWN = "UNKNOWN"


class RecyclingFeePowerSource(StrEnum):
    """Источник мощности, допустимый нормативными правилами."""

    ENGINE_POWER_KW = "ENGINE_POWER_KW"
    VEHICLE_MAXIMUM_POWER_KW = "VEHICLE_MAXIMUM_POWER_KW"
    MAX_30_MIN_ELECTRIC_POWER_KW = "MAX_30_MIN_ELECTRIC_POWER_KW"
    ENGINE_PLUS_MAX_30_MIN_ELECTRIC_POWER = (
        "ENGINE_PLUS_MAX_30_MIN_ELECTRIC_POWER"
    )


@dataclass(frozen=True)
class RecyclingFeePowerSelection:
    """Результат выбора нормативной мощности без предположений."""

    powertrain_type: RecyclingFeePowertrainType
    power_kw: Decimal | None
    source: RecyclingFeePowerSource | None
    missing_fields: tuple[str, ...] = ()


ICE_ENERGY_TYPES = frozenset(
    {
        "GASOLINE",
        "DIESEL",
        "NATURAL_GAS",
        "CNG",
        "GASOLINE_CNG",
    }
)
HEV_ENERGY_TYPES = frozenset(
    {
        "HEV",
        "METHANOL_HEV",
        "GASOLINE_MHEV_24V",
        "GASOLINE_MHEV_48V",
        "GASOLINE_MHEV_90V",
        "DIESEL_MHEV_48V",
    }
)
SERIES_HEV_ENERGY_TYPES = frozenset(
    {
        "SERIES_HEV",
        "汽油电驱",
        "Последовательный бензиновый гибрид",
    }
)


def classify_recycling_fee_powertrain(
    energy_type: str | None,
) -> RecyclingFeePowertrainType:
    """Классифицировать силовую установку, не смешивая схему и зарядку."""
    if energy_type in ICE_ENERGY_TYPES:
        return RecyclingFeePowertrainType.ICE
    if energy_type in HEV_ENERGY_TYPES:
        return RecyclingFeePowertrainType.HEV
    if energy_type == "PHEV":
        return RecyclingFeePowertrainType.PHEV
    if energy_type in SERIES_HEV_ENERGY_TYPES:
        return RecyclingFeePowertrainType.SERIES_HEV
    if energy_type == "EREV":
        return RecyclingFeePowertrainType.EREV
    if energy_type == "BEV":
        return RecyclingFeePowertrainType.EV
    return RecyclingFeePowertrainType.UNKNOWN


def select_recycling_fee_power(
    energy_type: str | None,
    *,
    engine_power_kw: Decimal | None = None,
    maximum_power_kw: Decimal | None = None,
    electric_30_min_power_kw: Decimal | None = None,
    phev_is_series: bool | None = None,
) -> RecyclingFeePowerSelection:
    """Выбрать мощность по ПП РФ № 1291 в редакции ПП РФ № 1713.

    Пиковая мощность электромоторов и системная мощность намеренно не
    принимаются: норматив требует максимальную 30-минутную мощность из
    документов о соответствии или электронного ПТС.
    """
    powertrain_type = classify_recycling_fee_powertrain(energy_type)

    if powertrain_type == RecyclingFeePowertrainType.ICE:
        if engine_power_kw is not None:
            return RecyclingFeePowerSelection(
                powertrain_type,
                engine_power_kw,
                RecyclingFeePowerSource.ENGINE_POWER_KW,
            )
        if maximum_power_kw is not None:
            return RecyclingFeePowerSelection(
                powertrain_type,
                maximum_power_kw,
                RecyclingFeePowerSource.VEHICLE_MAXIMUM_POWER_KW,
            )
        return RecyclingFeePowerSelection(
            powertrain_type, None, None, ("engine_power_kw",)
        )

    if powertrain_type == RecyclingFeePowertrainType.PHEV:
        if phev_is_series is None:
            return RecyclingFeePowerSelection(
                powertrain_type, None, None, ("phev_hybrid_architecture",)
            )
        powertrain_type = (
            RecyclingFeePowertrainType.SERIES_HEV
            if phev_is_series
            else RecyclingFeePowertrainType.PHEV
        )

    if powertrain_type in {
        RecyclingFeePowertrainType.EV,
        RecyclingFeePowertrainType.EREV,
        RecyclingFeePowertrainType.SERIES_HEV,
    }:
        if electric_30_min_power_kw is None:
            return RecyclingFeePowerSelection(
                powertrain_type,
                None,
                None,
                ("electric_30_min_power_kw",),
            )
        return RecyclingFeePowerSelection(
            powertrain_type,
            electric_30_min_power_kw,
            RecyclingFeePowerSource.MAX_30_MIN_ELECTRIC_POWER_KW,
        )

    if powertrain_type in {
        RecyclingFeePowertrainType.HEV,
        RecyclingFeePowertrainType.PHEV,
    }:
        missing = []
        if engine_power_kw is None:
            missing.append("engine_power_kw")
        if electric_30_min_power_kw is None:
            missing.append("electric_30_min_power_kw")
        if missing:
            return RecyclingFeePowerSelection(
                powertrain_type, None, None, tuple(missing)
            )
        return RecyclingFeePowerSelection(
            powertrain_type,
            engine_power_kw + electric_30_min_power_kw,
            RecyclingFeePowerSource.ENGINE_PLUS_MAX_30_MIN_ELECTRIC_POWER,
        )

    return RecyclingFeePowerSelection(
        powertrain_type, None, None, ("recycling_fee_powertrain_type",)
    )
