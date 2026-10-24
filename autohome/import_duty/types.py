from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ImporterType(StrEnum):
    """Категория импортёра."""

    INDIVIDUAL = "INDIVIDUAL"
    LEGAL_ENTITY = "LEGAL_ENTITY"


class CalculationStatus(StrEnum):
    """Состояние результата расчёта."""

    CALCULATED = "CALCULATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING_DATA = "MISSING_DATA"
    UNSUPPORTED = "UNSUPPORTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ClassificationStatus(StrEnum):
    """Состояние товарной классификации автомобиля."""

    CLASSIFIED = "CLASSIFIED"
    NOT_REQUIRED = "NOT_REQUIRED"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING_DATA = "MISSING_DATA"
    UNSUPPORTED = "UNSUPPORTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(frozen=True)
class ExchangeRate:
    """Официальный курс валюты с учётом номинала публикации."""

    currency: str
    nominal: int
    rate_rub: Decimal
    rate_date: date

    def __post_init__(self) -> None:
        if self.nominal <= 0:
            raise ValueError("Номинал валютного курса должен быть положительным")
        if self.rate_rub <= 0:
            raise ValueError("Валютный курс должен быть положительным")

    @property
    def rub_per_unit(self) -> Decimal:
        return self.rate_rub / Decimal(self.nominal)


@dataclass(frozen=True)
class DutyContext:
    """Подготовленные входные данные одного расчёта пошлины."""

    spec_id: int
    importer_type: ImporterType
    calculation_date: date
    price_cny: Decimal | None
    cny_rate: ExchangeRate
    eur_rate: ExchangeRate
    model_year: int | None
    energy_type: str | None
    body_type: str | None
    engine_displacement_cc: int | None
    engine_power_hp: Decimal | None = None
    motor_power_kw: Decimal | None = None
    price_source: str | None = None
    tnved_heading: str | None = None
    gross_mass_kg: int | None = None
    seat_count_max: int | None = None
    is_special_purpose: bool | None = None


@dataclass(frozen=True)
class DutyResult:
    """Результат расчёта одной ввозной пошлины."""

    status: CalculationStatus
    classification_status: ClassificationStatus
    amount_rub: Decimal | None = None
    rule_code: str | None = None
    tnved_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, str]] = field(default_factory=list)
