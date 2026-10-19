"""Классификация транспорта и расчёт ввозной пошлины Китай → Россия."""

from .calculator import calculate_import_duty
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
    "classify_vehicle",
)
