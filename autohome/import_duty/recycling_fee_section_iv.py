from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .recycling_fee import RecyclingFeeResult
from .recycling_fee_regulation import RECYCLING_FEE_REGULATION_SOURCE
from .types import CalculationStatus

SECTION_IV_BASE_RATE_RUB = Decimal(150000)
SECTION_IV_RULES_VERSION = "RU-RECYCLING-FEE-SECTION-IV-2026-v1"

ELECTRIC_POWERTRAINS = frozenset({"EV", "EREV", "SERIES_HEV"})
COMBUSTION_POWERTRAINS = frozenset({"ICE", "HEV", "PHEV"})


@dataclass(frozen=True)
class SectionIVRecyclingFeeContext:
    calculation_date: date
    vehicle_technical_category: str | None
    age_months: int | None
    powertrain_type: str | None
    engine_displacement_cc: int | None
    regular_route_use: bool = False
    regular_route_confirmation: bool | None = None


# Объем ДВС: верхняя граница диапазона, коэффициент нового ТС,
# коэффициент ТС старше трех лет. None означает диапазон свыше 10 000 см3.
SECTION_IV_COMBUSTION_COEFFICIENTS_2026 = (
    (2500, Decimal("6.46"), Decimal("6.54")),
    (5000, Decimal("22.73"), Decimal("34.41")),
    (10000, Decimal("25.38"), Decimal("32.58")),
    (None, Decimal("29.35"), Decimal("46.2")),
)

SECTION_IV_ELECTRIC_COEFFICIENTS_2026 = (Decimal("20.57"), Decimal("20.76"))
SECTION_IV_REGULAR_ROUTE_COEFFICIENTS_2026 = {
    10000: (Decimal("12.34"), Decimal("15.84")),
    None: (Decimal("14.27"), Decimal("22.46")),
}


def _common() -> dict[str, str]:
    return {
        "source": RECYCLING_FEE_REGULATION_SOURCE,
        "rules_version": SECTION_IV_RULES_VERSION,
        "regulatory_section": "SECTION_IV_M",
    }


def _combustion_band(
    engine_displacement_cc: int,
) -> tuple[int | None, Decimal, Decimal]:
    for row in SECTION_IV_COMBUSTION_COEFFICIENTS_2026:
        upper_bound = row[0]
        if upper_bound is None or engine_displacement_cc <= upper_bound:
            return row
    raise AssertionError("Диапазоны объема должны завершаться открытой границей")


def calculate_section_iv_recycling_fee(
    context: SectionIVRecyclingFeeContext,
) -> RecyclingFeeResult:
    """Рассчитать утильсбор по разделу IV для готовых M2/M3."""
    common = _common()
    if context.calculation_date.year != 2026:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "UNSUPPORTED_RATE_YEAR"},
        )
    if context.vehicle_technical_category not in {"M2", "M3"}:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "SECTION_IV_REQUIRES_M2_OR_M3_CATEGORY"},
        )

    missing = []
    if context.age_months is None:
        missing.append("age_months")
    if context.powertrain_type is None:
        missing.append("recycling_fee_powertrain_type")
    if missing:
        return RecyclingFeeResult(
            status=CalculationStatus.MISSING_DATA,
            details={**common, "missing_fields": missing},
        )

    if context.powertrain_type in ELECTRIC_POWERTRAINS:
        if context.regular_route_use:
            return RecyclingFeeResult(
                status=CalculationStatus.MANUAL_REVIEW,
                details={
                    **common,
                    "reason": "REGULAR_ROUTE_RATE_REQUIRES_COMBUSTION_VOLUME_BAND",
                },
            )
        coefficients = SECTION_IV_ELECTRIC_COEFFICIENTS_2026
        volume_band = None
        rule_code = "RECYCLING_FEE_SECTION_IV_ELECTRIC_2026"
    elif context.powertrain_type in COMBUSTION_POWERTRAINS:
        if context.engine_displacement_cc is None:
            return RecyclingFeeResult(
                status=CalculationStatus.MISSING_DATA,
                details={**common, "missing_fields": ["engine_displacement_cc"]},
            )
        if context.engine_displacement_cc <= 0:
            return RecyclingFeeResult(
                status=CalculationStatus.MANUAL_REVIEW,
                details={**common, "reason": "INVALID_ENGINE_DISPLACEMENT"},
            )
        volume_band, new_coefficient, old_coefficient = _combustion_band(
            context.engine_displacement_cc
        )
        coefficients = (new_coefficient, old_coefficient)
        rule_code = "RECYCLING_FEE_SECTION_IV_COMBUSTION_2026"
        if context.regular_route_use:
            if context.regular_route_confirmation is not True:
                return RecyclingFeeResult(
                    status=CalculationStatus.MANUAL_REVIEW,
                    details={
                        **common,
                        "reason": "REGULAR_ROUTE_CONFIRMATION_REQUIRED",
                    },
                )
            if context.engine_displacement_cc <= 5000:
                return RecyclingFeeResult(
                    status=CalculationStatus.MANUAL_REVIEW,
                    details={
                        **common,
                        "reason": "REGULAR_ROUTE_VOLUME_OUT_OF_RATE_SCOPE",
                    },
                )
            regular_band = 10000 if context.engine_displacement_cc <= 10000 else None
            coefficients = SECTION_IV_REGULAR_ROUTE_COEFFICIENTS_2026[regular_band]
            volume_band = regular_band
            rule_code = "RECYCLING_FEE_SECTION_IV_REGULAR_ROUTE_2026"
    else:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "UNSUPPORTED_POWERTRAIN_TYPE"},
        )

    coefficient = coefficients[1 if context.age_months > 36 else 0]
    amount = (SECTION_IV_BASE_RATE_RUB * coefficient).quantize(Decimal("0.01"))
    if context.powertrain_type in ELECTRIC_POWERTRAINS:
        volume_band_code = "ELECTRIC_OR_SERIES_HYBRID"
    elif volume_band is None:
        volume_band_code = "OVER_10000"
    else:
        volume_band_code = f"UP_TO_{volume_band}"
    return RecyclingFeeResult(
        status=CalculationStatus.CALCULATED,
        amount_rub=amount,
        rule_code=rule_code,
        details={
            **common,
            "formula": "base_rate_rub * coefficient",
            "base_rate_rub": str(SECTION_IV_BASE_RATE_RUB),
            "coefficient": str(coefficient),
            "recycling_fee_rub": str(amount),
            "vehicle_technical_category": context.vehicle_technical_category,
            "powertrain_type": context.powertrain_type,
            "engine_displacement_cc": context.engine_displacement_cc,
            "engine_displacement_band": volume_band_code,
            "age_months": context.age_months,
            "regular_route_use": context.regular_route_use,
            "regular_route_confirmation": context.regular_route_confirmation,
        },
    )
