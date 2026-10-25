"""Расчёт НДС при коммерческом ввозе автомобиля."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .types import CalculationStatus
from .vat_rates import (
    VAT_BASE_RULES_SOURCE,
    VAT_RATE_RULES_SOURCE,
    VAT_RULES_VERSION,
    vat_rate_for_date,
)

MONEY = Decimal("0.01")


@dataclass(frozen=True)
class VatContext:
    """Входные данные НДС для заранее признанного применимым ввоза."""

    calculation_date: date
    customs_value_rub: Decimal | None
    import_duty_rub: Decimal | None
    excise_rub: Decimal | None


@dataclass(frozen=True)
class VatResult:
    """Результат расчёта НДС без проверки категории импортёра."""

    status: CalculationStatus
    amount_rub: Decimal | None = None
    rule_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def calculate_vat(context: VatContext) -> VatResult:
    """Рассчитать НДС из таможенной стоимости, пошлины и акциза."""
    common_details = {
        "rate_source": VAT_RATE_RULES_SOURCE,
        "tax_base_source": VAT_BASE_RULES_SOURCE,
        "rules_version": VAT_RULES_VERSION,
    }
    rate = vat_rate_for_date(context.calculation_date)
    if rate is None:
        return VatResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common_details, "reason": "UNSUPPORTED_RATE_DATE"},
        )

    values = {
        "customs_value_rub": context.customs_value_rub,
        "import_duty_rub": context.import_duty_rub,
        "excise_rub": context.excise_rub,
    }
    missing_fields = [name for name, value in values.items() if value is None]
    if missing_fields:
        return VatResult(
            status=CalculationStatus.MISSING_DATA,
            details={**common_details, "missing_fields": missing_fields},
        )

    invalid_fields = [
        name
        for name, value in values.items()
        if value < 0 or (name == "customs_value_rub" and value == 0)
    ]
    if invalid_fields:
        return VatResult(
            status=CalculationStatus.MISSING_DATA,
            details={**common_details, "invalid_fields": invalid_fields},
        )

    tax_base = sum(values.values(), Decimal(0))
    amount = (tax_base * rate.rate).quantize(MONEY, rounding=ROUND_HALF_UP)
    return VatResult(
        status=CalculationStatus.CALCULATED,
        amount_rub=amount,
        rule_code=rate.rule_code,
        details={
            **common_details,
            "formula": (
                "(customs_value_rub + import_duty_rub + excise_rub) * vat_rate"
            ),
            "customs_value_rub": str(context.customs_value_rub),
            "import_duty_rub": str(context.import_duty_rub),
            "excise_rub": str(context.excise_rub),
            "tax_base_rub": str(tax_base),
            "vat_rate": str(rate.rate),
            "vat_rate_percent": str(rate.rate * Decimal(100)),
            "amount_rub": str(amount),
        },
    )
