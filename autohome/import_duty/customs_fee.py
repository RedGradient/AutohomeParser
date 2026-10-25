from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from .types import CalculationStatus

CUSTOMS_FEE_RULES_VERSION = "RU-CUSTOMS-FEE-2026-01-01-v1"
CUSTOMS_FEE_RULES_SOURCE = "https://www.consultant.ru/document/cons_doc_LAW_491874/"


@dataclass(frozen=True)
class CustomsFeeRate:
    max_customs_value_rub: Decimal | None
    fee_rub: Decimal
    rule_code: str


@dataclass(frozen=True)
class CustomsFeeResult:
    status: CalculationStatus
    amount_rub: Decimal | None = None
    rule_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomsFeeRatePeriod:
    """Период действия одной шкалы таможенного сбора."""

    effective_from: date
    effective_to: date | None
    rates: tuple[CustomsFeeRate, ...]
    rules_version: str


# С 1 января 2026 года сбор за таможенные операции при ввозе выбирается
# по общей таможенной стоимости товаров, заявленных в декларации.
CUSTOMS_FEE_RATES_2026 = (
    CustomsFeeRate(Decimal(200000), Decimal(1231), "CUSTOMS_FEE_2026_UP_TO_200K"),
    CustomsFeeRate(Decimal(450000), Decimal(2462), "CUSTOMS_FEE_2026_200K_450K"),
    CustomsFeeRate(Decimal(1200000), Decimal(4924), "CUSTOMS_FEE_2026_450K_1200K"),
    CustomsFeeRate(Decimal(2700000), Decimal(13541), "CUSTOMS_FEE_2026_1200K_2700K"),
    CustomsFeeRate(Decimal(4200000), Decimal(18465), "CUSTOMS_FEE_2026_2700K_4200K"),
    CustomsFeeRate(Decimal(5500000), Decimal(21344), "CUSTOMS_FEE_2026_4200K_5500K"),
    CustomsFeeRate(Decimal(10000000), Decimal(49240), "CUSTOMS_FEE_2026_5500K_10000K"),
    CustomsFeeRate(None, Decimal(73860), "CUSTOMS_FEE_2026_OVER_10000K"),
)

CUSTOMS_FEE_RATE_PERIODS = (
    CustomsFeeRatePeriod(
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        rates=CUSTOMS_FEE_RATES_2026,
        rules_version=CUSTOMS_FEE_RULES_VERSION,
    ),
)


def _rate_period(calculation_date: date) -> CustomsFeeRatePeriod | None:
    """Выбрать шкалу, действующую на дату расчёта."""
    for period in CUSTOMS_FEE_RATE_PERIODS:
        if calculation_date < period.effective_from:
            continue
        if period.effective_to is None or calculation_date <= period.effective_to:
            return period
    return None


def calculate_customs_fee(
    customs_value_rub: Decimal | None,
    calculation_date: date,
) -> CustomsFeeResult:
    """Рассчитать сбор по оценочной таможенной стоимости автомобиля."""
    period = _rate_period(calculation_date)
    common_details = {
        "source": CUSTOMS_FEE_RULES_SOURCE,
        "rules_version": period.rules_version if period is not None else None,
        "customs_value_source": "VEHICLE_PRICE_ONLY",
    }
    if period is None:
        return CustomsFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common_details, "reason": "UNSUPPORTED_RATE_DATE"},
        )
    if customs_value_rub is None or customs_value_rub <= 0:
        return CustomsFeeResult(
            status=CalculationStatus.MISSING_DATA,
            details={
                **common_details,
                "missing_fields": ["customs_value_rub"],
            },
        )

    for rate in period.rates:
        if (
            rate.max_customs_value_rub is None
            or customs_value_rub <= rate.max_customs_value_rub
        ):
            return CustomsFeeResult(
                status=CalculationStatus.CALCULATED,
                amount_rub=rate.fee_rub.quantize(Decimal("0.01")),
                rule_code=rate.rule_code,
                details={
                    **common_details,
                    "formula": "rate_by_customs_value_band",
                    "customs_value_rub": str(customs_value_rub),
                    "upper_bound_rub": (
                        str(rate.max_customs_value_rub)
                        if rate.max_customs_value_rub is not None
                        else None
                    ),
                    "fee_rub": str(rate.fee_rub.quantize(Decimal("0.01"))),
                },
            )

    raise AssertionError("Таблица ставок должна завершаться открытым диапазоном")
