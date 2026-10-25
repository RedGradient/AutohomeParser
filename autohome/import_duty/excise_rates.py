"""Версионируемые ставки акциза на легковые автомобили."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

EXCISE_RULES_VERSION = "RU-EXCISE-PASSENGER-CARS-2026-2028-v1"
EXCISE_RULES_SOURCE = (
    "https://www.consultant.ru/document/cons_doc_LAW_28165/"
    "22201a65e4f59a582714243c15b655989bd57066/"
)


@dataclass(frozen=True)
class ExciseRate:
    """Одна ставка акциза для диапазона мощности и календарного года."""

    max_power_kw: Decimal | None
    rate_rub_per_power_unit: Decimal
    rule_code: str


# Ставка установлена за каждые 0,75 кВт (1 л. с.). Верхняя граница
# включается в диапазон; None обозначает открытый последний диапазон.
EXCISE_RATES_BY_YEAR = {
    2026: (
        ExciseRate(Decimal("67.5"), Decimal(0), "EXCISE_M1_2026_UP_TO_90_HP"),
        ExciseRate(Decimal("112.5"), Decimal(64), "EXCISE_M1_2026_90_150_HP"),
        ExciseRate(Decimal(150), Decimal(613), "EXCISE_M1_2026_150_200_HP"),
        ExciseRate(Decimal(225), Decimal(1004), "EXCISE_M1_2026_200_300_HP"),
        ExciseRate(Decimal(300), Decimal(1711), "EXCISE_M1_2026_300_400_HP"),
        ExciseRate(Decimal(375), Decimal(1771), "EXCISE_M1_2026_400_500_HP"),
        ExciseRate(None, Decimal(1829), "EXCISE_M1_2026_OVER_500_HP"),
    ),
    2027: (
        ExciseRate(Decimal("67.5"), Decimal(0), "EXCISE_M1_2027_UP_TO_90_HP"),
        ExciseRate(Decimal("112.5"), Decimal(67), "EXCISE_M1_2027_90_150_HP"),
        ExciseRate(Decimal(150), Decimal(638), "EXCISE_M1_2027_150_200_HP"),
        ExciseRate(Decimal(225), Decimal(1044), "EXCISE_M1_2027_200_300_HP"),
        ExciseRate(Decimal(300), Decimal(1779), "EXCISE_M1_2027_300_400_HP"),
        ExciseRate(Decimal(375), Decimal(1842), "EXCISE_M1_2027_400_500_HP"),
        ExciseRate(None, Decimal(1902), "EXCISE_M1_2027_OVER_500_HP"),
    ),
    2028: (
        ExciseRate(Decimal("67.5"), Decimal(0), "EXCISE_M1_2028_UP_TO_90_HP"),
        ExciseRate(Decimal("112.5"), Decimal(70), "EXCISE_M1_2028_90_150_HP"),
        ExciseRate(Decimal(150), Decimal(664), "EXCISE_M1_2028_150_200_HP"),
        ExciseRate(Decimal(225), Decimal(1086), "EXCISE_M1_2028_200_300_HP"),
        ExciseRate(Decimal(300), Decimal(1850), "EXCISE_M1_2028_300_400_HP"),
        ExciseRate(Decimal(375), Decimal(1916), "EXCISE_M1_2028_400_500_HP"),
        ExciseRate(None, Decimal(1978), "EXCISE_M1_2028_OVER_500_HP"),
    ),
}


def excise_rate_for_power(year: int, power_kw: Decimal) -> ExciseRate | None:
    """Найти ставку для года и нормативной мощности в киловаттах."""
    rates = EXCISE_RATES_BY_YEAR.get(year)
    if rates is None:
        return None
    return next(
        rate
        for rate in rates
        if rate.max_power_kw is None or power_kw <= rate.max_power_kw
    )


def has_excise_rates(year: int) -> bool:
    """Проверить наличие утверждённых ставок для календарного года."""
    return year in EXCISE_RATES_BY_YEAR
