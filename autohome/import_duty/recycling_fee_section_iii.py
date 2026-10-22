from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .recycling_fee import RecyclingFeeResult
from .recycling_fee_regulation import RECYCLING_FEE_REGULATION_SOURCE
from .types import CalculationStatus

SECTION_III_BASE_RATE_RUB = Decimal(150000)
SECTION_III_RULES_VERSION = "RU-RECYCLING-FEE-SECTION-III-2026-v1"


@dataclass(frozen=True)
class SectionIIIRecyclingFeeContext:
    calculation_date: date
    vehicle_technical_category: str | None
    age_months: int | None
    gross_mass_kg: int | None
    is_special_purpose: bool | None
    vehicle_purpose_type: str | None = None


# Категория, нижняя исключительная и верхняя включительная границы массы,
# коэффициенты для нового ТС и ТС старше трех лет.
SECTION_III_COEFFICIENTS_2026 = (
    ("N1", None, 3500, Decimal("6.6"), Decimal("9.61")),
    ("N2", 3500, 5000, Decimal("6.91"), Decimal("10.29")),
    ("N2", 5000, 8000, Decimal("7.2"), Decimal("16.46")),
    ("N2", 8000, 12000, Decimal("10.2"), Decimal("27.81")),
    ("N3", 12000, 20000, Decimal("11.58"), Decimal("40.46")),
    ("N3", 20000, None, Decimal("31.53"), Decimal("66.44")),
    ("M2", None, 5000, Decimal("22.73"), Decimal("34.41")),
    ("M3", 5000, None, Decimal("25.38"), Decimal("32.58")),
)


def _common() -> dict[str, str]:
    return {
        "source": RECYCLING_FEE_REGULATION_SOURCE,
        "rules_version": SECTION_III_RULES_VERSION,
        "regulatory_section": "SECTION_III_SPECIAL",
    }


def _coefficient_row(
    category: str,
    gross_mass_kg: int,
) -> tuple[str, int | None, int | None, Decimal, Decimal] | None:
    for row in SECTION_III_COEFFICIENTS_2026:
        row_category, lower_bound, upper_bound, _, _ = row
        if row_category != category:
            continue
        above_lower = lower_bound is None or gross_mass_kg > lower_bound
        below_upper = upper_bound is None or gross_mass_kg <= upper_bound
        if above_lower and below_upper:
            return row
    return None


def calculate_section_iii_recycling_fee(
    context: SectionIIIRecyclingFeeContext,
) -> RecyclingFeeResult:
    """Рассчитать утильсбор по разделу III для готовой спецтехники."""
    common = _common()
    if context.calculation_date.year != 2026:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "UNSUPPORTED_RATE_YEAR"},
        )
    if context.vehicle_technical_category not in {"M2", "M3", "N1", "N2", "N3"}:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "SECTION_III_REQUIRES_COMMERCIAL_CATEGORY"},
        )
    if context.is_special_purpose is not True:
        reason = (
            "SPECIAL_PURPOSE_CONFIRMATION_REQUIRED"
            if context.is_special_purpose is None
            else "SECTION_III_REQUIRES_SPECIAL_PURPOSE_VEHICLE"
        )
        status = (
            CalculationStatus.MISSING_DATA
            if context.is_special_purpose is None
            else CalculationStatus.UNSUPPORTED
        )
        return RecyclingFeeResult(
            status=status,
            details={**common, "reason": reason},
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

    row = _coefficient_row(
        context.vehicle_technical_category,
        context.gross_mass_kg,
    )
    if row is None:
        return RecyclingFeeResult(
            status=CalculationStatus.MANUAL_REVIEW,
            details={
                **common,
                "reason": "TECHNICAL_CATEGORY_AND_GROSS_MASS_CONFLICT",
                "vehicle_technical_category": context.vehicle_technical_category,
                "gross_mass_kg": context.gross_mass_kg,
            },
        )

    _, lower_bound, upper_bound, new_coefficient, old_coefficient = row
    coefficient = old_coefficient if context.age_months > 36 else new_coefficient
    amount = (SECTION_III_BASE_RATE_RUB * coefficient).quantize(Decimal("0.01"))
    if lower_bound is None:
        mass_band = f"UP_TO_{upper_bound}"
    elif upper_bound is None:
        mass_band = f"OVER_{lower_bound}"
    else:
        mass_band = f"OVER_{lower_bound}_UP_TO_{upper_bound}"
    return RecyclingFeeResult(
        status=CalculationStatus.CALCULATED,
        amount_rub=amount,
        rule_code="RECYCLING_FEE_SECTION_III_SPECIAL_BY_CATEGORY_AND_MASS_2026",
        details={
            **common,
            "formula": "base_rate_rub * coefficient",
            "base_rate_rub": str(SECTION_III_BASE_RATE_RUB),
            "coefficient": str(coefficient),
            "recycling_fee_rub": str(amount),
            "vehicle_technical_category": context.vehicle_technical_category,
            "gross_mass_kg": context.gross_mass_kg,
            "gross_mass_band": mass_band,
            "age_months": context.age_months,
            "is_special_purpose": context.is_special_purpose,
            "vehicle_purpose_type": context.vehicle_purpose_type,
        },
    )
