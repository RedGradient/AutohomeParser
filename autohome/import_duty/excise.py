"""Выбор нормативной мощности и расчёт акциза для категории M1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from autohome.recycling_fee_power import (
    RecyclingFeePowerSource,
    RecyclingFeePowertrainType,
    classify_recycling_fee_powertrain,
)

from .excise_rates import (
    EXCISE_RULES_SOURCE,
    EXCISE_RULES_VERSION,
    excise_rate_for_power,
    has_excise_rates,
)
from .types import CalculationStatus

KW_PER_TAX_HP = Decimal("0.75")
MONEY = Decimal("0.01")


@dataclass(frozen=True)
class ExcisePowerSelection:
    """Выбранная нормативная мощность и её происхождение."""

    powertrain_type: str
    power_kw: Decimal | None
    power_hp: Decimal | None
    source: str | None
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExciseContext:
    """Входные данные расчёта акциза применимого автомобиля M1."""

    calculation_date: date
    energy_type: str | None
    engine_power_kw: Decimal | None = None
    engine_power_hp: Decimal | None = None
    normative_power_kw: Decimal | None = None
    normative_power_source: str | None = None


@dataclass(frozen=True)
class ExciseResult:
    """Результат расчёта акциза без проверки режима ввоза и категории."""

    status: CalculationStatus
    amount_rub: Decimal | None = None
    rule_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def select_excise_power(
    energy_type: str | None,
    *,
    engine_power_kw: Decimal | None = None,
    engine_power_hp: Decimal | None = None,
    normative_power_kw: Decimal | None = None,
    normative_power_source: str | None = None,
) -> ExcisePowerSelection:
    """Выбрать мощность, не подменяя нормативное значение пиковой мощностью."""
    powertrain_type = classify_recycling_fee_powertrain(energy_type)

    if powertrain_type == RecyclingFeePowertrainType.ICE:
        if engine_power_kw is not None and engine_power_kw > 0:
            return ExcisePowerSelection(
                powertrain_type.value,
                engine_power_kw,
                engine_power_kw / KW_PER_TAX_HP,
                RecyclingFeePowerSource.ENGINE_POWER_KW.value,
            )
        if engine_power_hp is not None and engine_power_hp > 0:
            return ExcisePowerSelection(
                powertrain_type.value,
                (engine_power_hp * KW_PER_TAX_HP).quantize(Decimal("0.001")),
                engine_power_hp,
                RecyclingFeePowerSource.ENGINE_POWER_HP_CONVERTED.value,
            )
        return ExcisePowerSelection(
            powertrain_type.value,
            None,
            None,
            None,
            ("engine_power_kw",),
        )

    accepted_sources = {
        RecyclingFeePowertrainType.EV: {
            RecyclingFeePowerSource.MAX_30_MIN_ELECTRIC_POWER_KW.value
        },
        RecyclingFeePowertrainType.EREV: {
            RecyclingFeePowerSource.MAX_30_MIN_ELECTRIC_POWER_KW.value
        },
        RecyclingFeePowertrainType.SERIES_HEV: {
            RecyclingFeePowerSource.MAX_30_MIN_ELECTRIC_POWER_KW.value
        },
        RecyclingFeePowertrainType.HEV: {
            RecyclingFeePowerSource.ENGINE_PLUS_MAX_30_MIN_ELECTRIC_POWER.value
        },
        RecyclingFeePowertrainType.PHEV: {
            RecyclingFeePowerSource.ENGINE_PLUS_MAX_30_MIN_ELECTRIC_POWER.value
        },
    }.get(powertrain_type, set())
    if (
        normative_power_kw is not None
        and normative_power_kw > 0
        and normative_power_source in accepted_sources
    ):
        return ExcisePowerSelection(
            powertrain_type.value,
            normative_power_kw,
            normative_power_kw / KW_PER_TAX_HP,
            normative_power_source,
        )

    if powertrain_type == RecyclingFeePowertrainType.UNKNOWN:
        return ExcisePowerSelection(
            powertrain_type.value,
            None,
            None,
            None,
            ("energy_type",),
        )
    return ExcisePowerSelection(
        powertrain_type.value,
        None,
        None,
        None,
        ("normative_power_kw", "normative_power_source"),
    )


def calculate_excise(context: ExciseContext) -> ExciseResult:
    """Рассчитать акциз для заранее признанного применимым автомобиля M1."""
    common_details = {
        "source": EXCISE_RULES_SOURCE,
        "rules_version": EXCISE_RULES_VERSION,
    }
    if not has_excise_rates(context.calculation_date.year):
        return ExciseResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common_details, "reason": "UNSUPPORTED_RATE_YEAR"},
        )

    selection = select_excise_power(
        context.energy_type,
        engine_power_kw=context.engine_power_kw,
        engine_power_hp=context.engine_power_hp,
        normative_power_kw=context.normative_power_kw,
        normative_power_source=context.normative_power_source,
    )
    if selection.power_kw is None or selection.power_hp is None:
        return ExciseResult(
            status=CalculationStatus.MISSING_DATA,
            details={
                **common_details,
                "powertrain_type": selection.powertrain_type,
                "missing_fields": list(selection.missing_fields),
            },
        )

    rate = excise_rate_for_power(context.calculation_date.year, selection.power_kw)
    assert rate is not None
    amount = (selection.power_hp * rate.rate_rub_per_power_unit).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )
    return ExciseResult(
        status=CalculationStatus.CALCULATED,
        amount_rub=amount,
        rule_code=rate.rule_code,
        details={
            **common_details,
            "formula": "power_hp * rate_rub_per_power_unit",
            "powertrain_type": selection.powertrain_type,
            "power_kw": str(selection.power_kw),
            "power_hp": str(selection.power_hp.quantize(Decimal("0.001"))),
            "power_source": selection.source,
            "rate_rub_per_power_unit": str(rate.rate_rub_per_power_unit),
            "amount_rub": str(amount),
        },
    )
