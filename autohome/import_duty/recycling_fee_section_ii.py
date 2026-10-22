from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from .recycling_fee import RecyclingFeeResult
from .recycling_fee_regulation import RECYCLING_FEE_REGULATION_SOURCE
from .types import CalculationStatus


SECTION_II_BASE_RATE_RUB = Decimal("150000")
SECTION_II_RULES_VERSION = "RU-RECYCLING-FEE-SECTION-II-2026-v1"


class SectionIIVehicleSubtype(StrEnum):
    GENERAL = "GENERAL"
    ROAD_TRACTOR = "ROAD_TRACTOR"
    DUMP_TRUCK = "DUMP_TRUCK"
    BOX_TRUCK = "BOX_TRUCK"
    INTERNATIONAL_ROAD_TRACTOR = "INTERNATIONAL_ROAD_TRACTOR"


@dataclass(frozen=True)
class SectionIIRecyclingFeeContext:
    calculation_date: date
    vehicle_technical_category: str | None
    age_months: int | None
    gross_mass_kg: int | None
    vehicle_subtype: SectionIIVehicleSubtype | None = None
    international_transport_confirmation: bool | None = None


# Верхняя граница массы и коэффициенты 2026 года
# (ТС не старше 3 лет, ТС старше 3 лет).
SECTION_II_GENERAL_COEFFICIENTS_2026 = (
    (2500, Decimal("6.13"), Decimal("8.91")),
    (3500, Decimal("6.6"), Decimal("9.61")),
    (5000, Decimal("6.91"), Decimal("10.29")),
    (8000, Decimal("7.2"), Decimal("16.46")),
    (12000, Decimal("10.2"), Decimal("27.81")),
    (20000, Decimal("11.58"), Decimal("40.46")),
    (None, Decimal("31.53"), Decimal("66.44")),
)


def _common() -> dict[str, str]:
    return {
        "source": RECYCLING_FEE_REGULATION_SOURCE,
        "rules_version": SECTION_II_RULES_VERSION,
        "regulatory_section": "SECTION_II_N",
    }


def _mass_band(gross_mass_kg: int) -> tuple[int | None, Decimal, Decimal]:
    for row in SECTION_II_GENERAL_COEFFICIENTS_2026:
        upper_bound = row[0]
        if upper_bound is None or gross_mass_kg <= upper_bound:
            return row
    raise AssertionError("Диапазоны массы должны завершаться открытой границей")


def calculate_section_ii_recycling_fee(
    context: SectionIIRecyclingFeeContext,
) -> RecyclingFeeResult:
    """Рассчитать утильсбор по разделу II для готовых N1/N2/N3."""
    common = _common()
    if context.calculation_date.year != 2026:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "UNSUPPORTED_RATE_YEAR"},
        )
    if context.vehicle_technical_category not in {"N1", "N2", "N3"}:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "SECTION_II_REQUIRES_N_CATEGORY"},
        )
    missing = []
    if context.age_months is None:
        missing.append("age_months")
    if context.gross_mass_kg is None:
        missing.append("gross_mass_kg")
    if missing:
        return RecyclingFeeResult(
            status=CalculationStatus.MISSING_DATA,
            details={**common, "missing_fields": missing},
        )
    if context.gross_mass_kg <= 0:
        return RecyclingFeeResult(
            status=CalculationStatus.MANUAL_REVIEW,
            details={**common, "reason": "INVALID_GROSS_MASS"},
        )

    upper_bound, new_coefficient, old_coefficient = _mass_band(context.gross_mass_kg)
    subtype = context.vehicle_subtype
    if 12000 < context.gross_mass_kg <= 20000 and subtype is None:
        return RecyclingFeeResult(
            status=CalculationStatus.MANUAL_REVIEW,
            details={
                **common,
                "reason": "VEHICLE_SUBTYPE_REQUIRED_FOR_12_TO_20_TONNES",
                "missing_fields": ["section_ii_vehicle_subtype"],
            },
        )

    if subtype == SectionIIVehicleSubtype.INTERNATIONAL_ROAD_TRACTOR:
        if context.international_transport_confirmation is not True:
            return RecyclingFeeResult(
                status=CalculationStatus.MANUAL_REVIEW,
                details={
                    **common,
                    "reason": "INTERNATIONAL_TRANSPORT_CONFIRMATION_REQUIRED",
                },
            )
        if context.gross_mass_kg <= 12000:
            return RecyclingFeeResult(
                status=CalculationStatus.MANUAL_REVIEW,
                details={
                    **common,
                    "reason": "INTERNATIONAL_TRACTOR_MASS_OUT_OF_RANGE",
                },
            )
        coefficients = (
            (Decimal("5.67"), Decimal("23.13"))
            if context.gross_mass_kg <= 20000
            else (Decimal("6.68"), Decimal("13.57"))
        )
        rule_code = "RECYCLING_FEE_SECTION_II_INTERNATIONAL_TRACTOR_2026"
    elif (
        subtype == SectionIIVehicleSubtype.ROAD_TRACTOR
        and 12000 < context.gross_mass_kg <= 20000
    ):
        coefficients = (Decimal("19.83"), Decimal("80.88"))
        rule_code = "RECYCLING_FEE_SECTION_II_ROAD_TRACTOR_2026"
    else:
        coefficients = (new_coefficient, old_coefficient)
        rule_code = "RECYCLING_FEE_SECTION_II_GENERAL_2026"

    coefficient = coefficients[1 if context.age_months > 36 else 0]
    amount = (SECTION_II_BASE_RATE_RUB * coefficient).quantize(Decimal("0.01"))
    mass_band = f"UP_TO_{upper_bound}" if upper_bound is not None else "OVER_20000"
    return RecyclingFeeResult(
        status=CalculationStatus.CALCULATED,
        amount_rub=amount,
        rule_code=rule_code,
        details={
            **common,
            "formula": "base_rate_rub * coefficient",
            "base_rate_rub": str(SECTION_II_BASE_RATE_RUB),
            "coefficient": str(coefficient),
            "recycling_fee_rub": str(amount),
            "vehicle_technical_category": context.vehicle_technical_category,
            "gross_mass_kg": context.gross_mass_kg,
            "gross_mass_band": mass_band,
            "age_months": context.age_months,
            "vehicle_subtype": subtype or SectionIIVehicleSubtype.GENERAL,
            "international_transport_confirmation": (
                context.international_transport_confirmation
            ),
        },
    )
