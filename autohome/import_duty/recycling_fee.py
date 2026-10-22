from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import re
from typing import Any

from .types import CalculationStatus, ImporterType


RECYCLING_FEE_RULES_VERSION = "RU-RECYCLING-FEE-M1-2026-v1"
RECYCLING_FEE_RULES_SOURCE = "https://www.consultant.ru/document/cons_doc_LAW_517977/"
RECYCLING_FEE_BASE_RUB = Decimal("20000")
PERSONAL_ICE_MAX_POWER_KW = Decimal("117.68")
PERSONAL_ELECTRIC_MAX_POWER_KW = Decimal("58.84")


@dataclass(frozen=True)
class RecyclingFeeContext:
    importer_type: ImporterType
    calculation_date: date
    personal_use: bool
    vehicle_technical_category: str | None
    age_months: int | None
    powertrain_type: str | None
    power_kw: Decimal | None
    power_source: str | None
    engine_displacement_cc: int | None
    engine_summary: str | None = None


@dataclass(frozen=True)
class RecyclingFeeResult:
    status: CalculationStatus
    amount_rub: Decimal | None = None
    rule_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


POWER_BAND_MAX_KW = (
    Decimal("51.48"),
    Decimal("73.55"),
    Decimal("95.61"),
    Decimal("117.68"),
    Decimal("139.75"),
    Decimal("161.81"),
    Decimal("183.88"),
    Decimal("205.94"),
    Decimal("228"),
    Decimal("250.07"),
    Decimal("272.13"),
    Decimal("294.20"),
    Decimal("316.26"),
    Decimal("338.33"),
    Decimal("367.75"),
    None,
)

# Коэффициенты 2026 года: (ТС не старше 3 лет, ТС старше 3 лет).
# Порядок строк соответствует POWER_BAND_MAX_KW.
COMMERCIAL_ICE_COEFFICIENTS_2026 = {
    1000: (
        *((Decimal("14.88"), Decimal("27.6")),) * 4,
        (Decimal("15.36"), Decimal("28.43")),
        (Decimal("15.84"), Decimal("29.28")),
        (Decimal("16.2"), Decimal("30.12")),
        *((Decimal("17.28"), Decimal("30.12")),) * 9,
    ),
    2000: (
        *((Decimal("40.04"), Decimal("70.44")),) * 4,
        (Decimal("45"), Decimal("74.64")),
        (Decimal("47.64"), Decimal("79.2")),
        (Decimal("50.52"), Decimal("83.88")),
        (Decimal("57.12"), Decimal("91.92")),
        (Decimal("64.56"), Decimal("100.56")),
        (Decimal("72.96"), Decimal("110.16")),
        (Decimal("83.16"), Decimal("120.6")),
        (Decimal("94.8"), Decimal("132")),
        (Decimal("108"), Decimal("144.6")),
        (Decimal("123.24"), Decimal("158.4")),
        (Decimal("140.4"), Decimal("173.4")),
        (Decimal("160.08"), Decimal("189.84")),
    ),
    3000: (
        *((Decimal("112.52"), Decimal("170.36")),) * 4,
        (Decimal("115.34"), Decimal("172.8")),
        (Decimal("118.2"), Decimal("175.08")),
        (Decimal("120.12"), Decimal("177.6")),
        (Decimal("126"), Decimal("183")),
        (Decimal("131.04"), Decimal("188.52")),
        (Decimal("136.32"), Decimal("193.68")),
        (Decimal("141.72"), Decimal("199.08")),
        (Decimal("147.48"), Decimal("204.72")),
        (Decimal("153.36"), Decimal("210.48")),
        (Decimal("159.48"), Decimal("216.36")),
        (Decimal("165.84"), Decimal("222.36")),
        (Decimal("172.44"), Decimal("228.6")),
    ),
    3500: (
        *((Decimal("129.2"), Decimal("197.81")),) * 4,
        (Decimal("131.76"), Decimal("200.04")),
        (Decimal("134.4"), Decimal("202.2")),
        (Decimal("137.16"), Decimal("204.36")),
        (Decimal("140.52"), Decimal("207.24")),
        (Decimal("144"), Decimal("212.4")),
        (Decimal("151.92"), Decimal("217.8")),
        (Decimal("160.32"), Decimal("224.28")),
        (Decimal("169.2"), Decimal("231")),
        (Decimal("178.44"), Decimal("237.96")),
        (Decimal("188.28"), Decimal("245.04")),
        (Decimal("198.6"), Decimal("252.48")),
        (Decimal("209.52"), Decimal("260.04")),
    ),
    None: (
        *((Decimal("164.53"), Decimal("216.29")),) * 4,
        (Decimal("167.28"), Decimal("219.48")),
        (Decimal("170.16"), Decimal("222.84")),
        (Decimal("173.04"), Decimal("226.2")),
        (Decimal("176.52"), Decimal("231.36")),
        (Decimal("180"), Decimal("236.64")),
        (Decimal("186.36"), Decimal("249.6")),
        (Decimal("192.88"), Decimal("263.4")),
        (Decimal("199.68"), Decimal("277.92")),
        (Decimal("206.64"), Decimal("293.16")),
        (Decimal("213.84"), Decimal("309.36")),
        (Decimal("221.28"), Decimal("326.4")),
        (Decimal("229.08"), Decimal("344.28")),
    ),
}

# Общие коэффициенты 2026 года для электромобилей и последовательных гибридов.
# После 205,94 кВт ставка одинакова для всех последующих диапазонов мощности.
GENERAL_ELECTRIC_COEFFICIENTS_2026 = (
    (Decimal("40.04"), Decimal("70.44")),
    (Decimal("49.56"), Decimal("82.08")),
    (Decimal("65.88"), Decimal("95.64")),
    (Decimal("78"), Decimal("111.36")),
    (Decimal("92.4"), Decimal("129.72")),
    (Decimal("109.68"), Decimal("151.2")),
    (Decimal("129.96"), Decimal("176.16")),
    (Decimal("153.96"), Decimal("205.2")),
    *((Decimal("182.4"), Decimal("239.04")),) * 8,
)


def _power_band_index(power_kw: Decimal) -> int:
    for index, upper_bound in enumerate(POWER_BAND_MAX_KW):
        if upper_bound is None or power_kw <= upper_bound:
            return index
    raise AssertionError("Диапазоны мощности должны завершаться открытой границей")


def _volume_band(engine_displacement_cc: int) -> int | None:
    for upper_bound in (1000, 2000, 3000, 3500):
        if engine_displacement_cc <= upper_bound:
            return upper_bound
    return None


def _volume_band_from_engine_summary(engine_summary: str | None) -> int | None:
    """Определить только нормативный диапазон по записи вида 2.0T/3.5L."""
    if not engine_summary:
        return None
    match = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*[LT]\b", engine_summary)
    if match is None:
        return None
    nominal_liters = Decimal(match.group(1).replace(",", "."))
    if nominal_liters <= Decimal("1"):
        return 1000
    if nominal_liters <= Decimal("2"):
        return 2000
    if nominal_liters <= Decimal("3"):
        return 3000
    if nominal_liters <= Decimal("3.5"):
        return 3500
    return 0


def _result(
    context: RecyclingFeeContext,
    coefficient: Decimal,
    rule_code: str,
) -> RecyclingFeeResult:
    amount = (RECYCLING_FEE_BASE_RUB * coefficient).quantize(Decimal("0.01"))
    return RecyclingFeeResult(
        status=CalculationStatus.CALCULATED,
        amount_rub=amount,
        rule_code=rule_code,
        details={
            "source": RECYCLING_FEE_RULES_SOURCE,
            "rules_version": RECYCLING_FEE_RULES_VERSION,
            "formula": "base_rate_rub * coefficient",
            "base_rate_rub": str(RECYCLING_FEE_BASE_RUB),
            "coefficient": str(coefficient),
            "recycling_fee_rub": str(amount),
            "personal_use": context.personal_use,
            "vehicle_technical_category": context.vehicle_technical_category,
            "powertrain_type": context.powertrain_type,
            "power_kw": str(context.power_kw),
            "power_source": context.power_source,
            "engine_displacement_cc": context.engine_displacement_cc,
            "age_months": context.age_months,
        },
    )


def calculate_recycling_fee(context: RecyclingFeeContext) -> RecyclingFeeResult:
    """Рассчитать поддерживаемые сценарии утильсбора категории M1 за 2026 год."""
    common = {
        "source": RECYCLING_FEE_RULES_SOURCE,
        "rules_version": RECYCLING_FEE_RULES_VERSION,
    }
    if context.calculation_date.year != 2026:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "UNSUPPORTED_RATE_YEAR"},
        )
    if context.vehicle_technical_category is None:
        return RecyclingFeeResult(
            status=CalculationStatus.MISSING_DATA,
            details={**common, "missing_fields": ["vehicle_technical_category"]},
        )
    if context.vehicle_technical_category != "M1":
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "ONLY_M1_SUPPORTED"},
        )
    missing = []
    if context.age_months is None:
        missing.append("age_months")
    if context.powertrain_type is None:
        missing.append("recycling_fee_powertrain_type")
    if context.power_kw is None:
        missing.append("recycling_fee_power_kw")
    if missing:
        return RecyclingFeeResult(
            status=CalculationStatus.MISSING_DATA,
            details={**common, "missing_fields": missing},
        )
    is_older = context.age_months > 36
    age_index = 1 if is_older else 0

    electric_branch = context.powertrain_type in {"EV", "EREV", "SERIES_HEV"}
    personal_limit = (
        PERSONAL_ELECTRIC_MAX_POWER_KW if electric_branch else PERSONAL_ICE_MAX_POWER_KW
    )
    if (
        context.importer_type == ImporterType.INDIVIDUAL
        and context.personal_use
        and context.power_kw <= personal_limit
    ):
        coefficient = Decimal("0.26") if is_older else Decimal("0.17")
        return _result(context, coefficient, "RECYCLING_FEE_M1_PERSONAL_PREFERENTIAL")

    if electric_branch:
        coefficient = GENERAL_ELECTRIC_COEFFICIENTS_2026[
            _power_band_index(context.power_kw)
        ][age_index]
        rule_code = (
            "RECYCLING_FEE_M1_PERSONAL_NON_PREFERENTIAL_2026"
            if context.importer_type == ImporterType.INDIVIDUAL and context.personal_use
            else "RECYCLING_FEE_M1_GENERAL_ELECTRIC_2026"
        )
        return _result(context, coefficient, rule_code)
    if context.powertrain_type not in {"ICE", "HEV", "PHEV"}:
        return RecyclingFeeResult(
            status=CalculationStatus.UNSUPPORTED,
            details={**common, "reason": "UNSUPPORTED_POWERTRAIN_TYPE"},
        )
    if context.engine_displacement_cc is not None:
        volume_band = _volume_band(context.engine_displacement_cc)
        volume_source = "ENGINE_DISPLACEMENT_CC"
    else:
        inferred_band = _volume_band_from_engine_summary(context.engine_summary)
        if inferred_band is None:
            return RecyclingFeeResult(
                status=CalculationStatus.MISSING_DATA,
                details={**common, "missing_fields": ["engine_displacement_cc"]},
            )
        volume_band = inferred_band or None
        volume_source = "ENGINE_SUMMARY_NOMINAL_VOLUME"
    coefficient = COMMERCIAL_ICE_COEFFICIENTS_2026[volume_band][
        _power_band_index(context.power_kw)
    ][age_index]
    rule_code = (
        "RECYCLING_FEE_M1_PERSONAL_NON_PREFERENTIAL_2026"
        if context.importer_type == ImporterType.INDIVIDUAL and context.personal_use
        else "RECYCLING_FEE_M1_COMMERCIAL_2026"
    )
    result = _result(context, coefficient, rule_code)
    result.details.update(
        {
            "engine_volume_band_cc": (
                f"UP_TO_{volume_band}" if volume_band is not None else "OVER_3500"
            ),
            "engine_volume_source": volume_source,
        }
    )
    return result
