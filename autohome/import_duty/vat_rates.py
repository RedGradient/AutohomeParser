"""Версионируемые ставки НДС при ввозе автомобилей."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

VAT_RULES_VERSION = "RU-IMPORT-VAT-2026-01-01-v1"
VAT_RATE_RULES_SOURCE = "https://www.nalog.gov.ru/new2026/"
VAT_BASE_RULES_SOURCE = (
    "https://www.consultant.ru/document/cons_doc_LAW_28165/"
    "89772e2c0ed2c4c82e26fdcfa069356922d887ee/"
)


@dataclass(frozen=True)
class VatRate:
    """Ставка НДС и дата начала её действия."""

    effective_from: date
    rate: Decimal
    rule_code: str


# Основная ставка НДС с 1 января 2026 года составляет 22%. Открытый период
# действия позволяет применять ставку после 2026 года до появления новой нормы.
VAT_RATES = (
    VatRate(
        effective_from=date(2026, 1, 1),
        rate=Decimal("0.22"),
        rule_code="VAT_IMPORT_STANDARD_22_FROM_2026",
    ),
)


def vat_rate_for_date(calculation_date: date) -> VatRate | None:
    """Найти последнюю ставку, действующую на дату расчёта."""
    applicable = (rate for rate in VAT_RATES if rate.effective_from <= calculation_date)
    return max(applicable, key=lambda rate: rate.effective_from, default=None)
