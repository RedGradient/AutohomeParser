"""Классификация транспорта и расчёт ввозной пошлины Китай → Россия."""

from .calculator import calculate_import_duty
from .customs_fee import calculate_customs_fee
from .classifier import (
    CLASSIFICATION_RULES_VERSION,
    VehicleClassificationInput,
    VehicleClassificationResult,
    classify_vehicle,
)
from .types import DutyContext, DutyResult, ExchangeRate, ImporterType

__all__ = (
    "CLASSIFICATION_RULES_VERSION",
    "DutyContext",
    "DutyResult",
    "ExchangeRate",
    "ImporterType",
    "VehicleClassificationInput",
    "VehicleClassificationResult",
    "calculate_import_duty",
    "calculate_customs_fee",
    "classify_vehicle",
)
