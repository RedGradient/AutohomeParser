from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .types import ClassificationStatus


CLASSIFICATION_RULES_VERSION = "RU-EAEU-VEHICLE-CLASSIFICATION-2026-01-22-v1"

PASSENGER_BODY_TYPES = frozenset(
    {
        "SEDAN",
        "HATCHBACK",
        "LIFTBACK",
        "WAGON",
        "CROSSOVER_WAGON",
        "SUV",
        "SPORTS_CAR",
        "COUPE",
        "CONVERTIBLE",
        "MPV",
    }
)
VAN_BODY_TYPES = frozenset({"VAN"})
PICKUP_BODY_TYPES = frozenset({"PICKUP"})
TRUCK_BODY_TYPES = frozenset({"TRUCK"})
SUPPORTED_BODY_TYPES = (
    PASSENGER_BODY_TYPES | VAN_BODY_TYPES | PICKUP_BODY_TYPES | TRUCK_BODY_TYPES
)

PASSENGER_CLASS_MARKERS = (
    "_CAR",
    "_SUV",
    "_MPV",
)
VAN_VEHICLE_CLASSES = frozenset({"MICROVAN", "LIGHT_COMMERCIAL_VAN"})
PICKUP_VEHICLE_CLASSES = frozenset({"PICKUP", "PREMIUM_PICKUP"})
TRUCK_VEHICLE_CLASSES = frozenset({"MINI_TRUCK", "LIGHT_TRUCK"})


@dataclass(frozen=True)
class VehicleClassificationInput:
    """Нормализованные признаки, используемые для выбора товарной позиции."""

    body_type: str | None
    vehicle_class: str | None
    seat_count_min: int | None = None
    seat_count_max: int | None = None
    gross_mass_kg: int | None = None
    curb_mass_kg: int | None = None
    payload_kg_min: int | None = None
    payload_kg_max: int | None = None
    length_mm: int | None = None
    wheelbase_mm: int | None = None
    cargo_length_min_mm: int | None = None
    cargo_length_max_mm: int | None = None
    cargo_width_min_mm: int | None = None
    cargo_width_max_mm: int | None = None
    cargo_height_min_mm: int | None = None
    cargo_height_max_mm: int | None = None
    has_permanent_rear_seats: bool | None = None
    has_rear_side_windows: bool | None = None
    has_rear_windowed_door: bool | None = None
    has_separate_cargo_compartment: bool | None = None
    is_special_purpose: bool | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> VehicleClassificationInput:
        """Создать вход из SQLAlchemy RowMapping или обычного словаря."""
        return cls(
            **{
                name: values.get(name)
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class VehicleClassificationResult:
    """Воспроизводимый результат безопасной классификации транспорта."""

    status: ClassificationStatus
    tnved_heading: str | None = None
    rule_code: str | None = None
    missing_fields: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    rules_version: str = CLASSIFICATION_RULES_VERSION


def _result(
    status: ClassificationStatus,
    *,
    heading: str | None = None,
    rule_code: str | None = None,
    missing_fields: list[str] | tuple[str, ...] = (),
    **details: Any,
) -> VehicleClassificationResult:
    return VehicleClassificationResult(
        status=status,
        tnved_heading=heading,
        rule_code=rule_code,
        missing_fields=tuple(sorted(missing_fields)),
        details=details,
    )


def _vehicle_family(vehicle_class: str | None) -> str | None:
    if vehicle_class is None:
        return None
    if vehicle_class in VAN_VEHICLE_CLASSES:
        return "VAN"
    if vehicle_class in PICKUP_VEHICLE_CLASSES:
        return "PICKUP"
    if vehicle_class in TRUCK_VEHICLE_CLASSES:
        return "TRUCK"
    if vehicle_class == "MPV" or vehicle_class.endswith(PASSENGER_CLASS_MARKERS):
        return "PASSENGER"
    return None


def _body_family(body_type: str) -> str | None:
    if body_type in PASSENGER_BODY_TYPES:
        return "PASSENGER"
    if body_type in VAN_BODY_TYPES:
        return "VAN"
    if body_type in PICKUP_BODY_TYPES:
        return "PICKUP"
    if body_type in TRUCK_BODY_TYPES:
        return "TRUCK"
    return None


def _seat_classification(
    values: VehicleClassificationInput,
) -> VehicleClassificationResult | str:
    missing = [
        name
        for name in ("seat_count_min", "seat_count_max")
        if getattr(values, name) is None
    ]
    if missing:
        return _result(
            ClassificationStatus.MISSING_DATA,
            missing_fields=missing,
            reason="SEAT_COUNT_REQUIRED",
        )
    assert values.seat_count_min is not None
    assert values.seat_count_max is not None
    if values.seat_count_min > values.seat_count_max:
        return _result(
            ClassificationStatus.AMBIGUOUS,
            reason="INVALID_SEAT_RANGE",
            seat_count_min=values.seat_count_min,
            seat_count_max=values.seat_count_max,
        )
    if values.seat_count_min < 10 <= values.seat_count_max:
        return _result(
            ClassificationStatus.AMBIGUOUS,
            reason="SEAT_RANGE_CROSSES_8702_BOUNDARY",
            seat_count_min=values.seat_count_min,
            seat_count_max=values.seat_count_max,
        )
    return "8702" if values.seat_count_min >= 10 else "8703"


def _classify_van(
    values: VehicleClassificationInput,
    seat_heading: str,
) -> VehicleClassificationResult:
    if seat_heading == "8702":
        return _result(
            ClassificationStatus.CLASSIFIED,
            heading="8702",
            rule_code="PASSENGER_VAN_AT_LEAST_10_SEATS",
        )

    fields = (
        "has_permanent_rear_seats",
        "has_rear_side_windows",
        "has_rear_windowed_door",
        "has_separate_cargo_compartment",
    )
    missing = [name for name in fields if getattr(values, name) is None]
    if missing:
        return _result(
            ClassificationStatus.MISSING_DATA,
            missing_fields=missing,
            reason="VAN_PURPOSE_FEATURES_REQUIRED",
        )
    if (
        values.has_permanent_rear_seats
        and values.has_rear_side_windows
        and values.has_rear_windowed_door
        and values.has_separate_cargo_compartment is False
    ):
        return _result(
            ClassificationStatus.CLASSIFIED,
            heading="8703",
            rule_code="PASSENGER_VAN_UP_TO_9_SEATS",
        )
    return _result(
        ClassificationStatus.MANUAL_REVIEW,
        reason="VAN_PASSENGER_OR_CARGO_PURPOSE_NOT_PROVEN",
    )


def _classify_pickup(
    values: VehicleClassificationInput,
) -> VehicleClassificationResult:
    required = (
        "seat_count_min",
        "seat_count_max",
        "gross_mass_kg",
        "curb_mass_kg",
        "payload_kg_min",
        "payload_kg_max",
        "length_mm",
        "wheelbase_mm",
        "cargo_length_min_mm",
        "cargo_length_max_mm",
        "cargo_width_min_mm",
        "cargo_width_max_mm",
        "cargo_height_min_mm",
        "cargo_height_max_mm",
        "has_permanent_rear_seats",
        "has_rear_side_windows",
        "has_rear_windowed_door",
        "has_separate_cargo_compartment",
        "is_special_purpose",
    )
    missing = [name for name in required if getattr(values, name) is None]
    if missing:
        return _result(
            ClassificationStatus.MISSING_DATA,
            missing_fields=missing,
            reason="PICKUP_CLASSIFICATION_FEATURES_REQUIRED",
        )
    return _result(
        ClassificationStatus.MANUAL_REVIEW,
        reason="PICKUP_8703_OR_8704_REQUIRES_DOCUMENT_REVIEW",
    )


def _classify_truck(
    values: VehicleClassificationInput,
) -> VehicleClassificationResult:
    missing = [
        name
        for name in ("gross_mass_kg", "is_special_purpose")
        if getattr(values, name) is None
    ]
    if missing:
        return _result(
            ClassificationStatus.MISSING_DATA,
            missing_fields=missing,
            reason="TRUCK_CLASSIFICATION_FEATURES_REQUIRED",
        )
    return _result(
        ClassificationStatus.CLASSIFIED,
        heading="8704",
        rule_code="ORDINARY_GOODS_VEHICLE",
        gross_mass_kg=values.gross_mass_kg,
    )


def classify_vehicle(
    values: VehicleClassificationInput,
) -> VehicleClassificationResult:
    """Определить безопасную товарную позицию 8702, 8703, 8704 либо отказ."""
    if values.is_special_purpose is True:
        return _result(
            ClassificationStatus.UNSUPPORTED,
            heading="8705",
            reason="SPECIAL_PURPOSE_VEHICLE_NOT_SUPPORTED",
        )
    missing = [
        name
        for name in ("body_type", "vehicle_class")
        if getattr(values, name) is None
    ]
    if missing:
        return _result(
            ClassificationStatus.MISSING_DATA,
            missing_fields=missing,
            reason="COMMON_CLASSIFICATION_FIELDS_REQUIRED",
        )
    assert values.body_type is not None
    assert values.vehicle_class is not None

    if values.body_type not in SUPPORTED_BODY_TYPES:
        return _result(
            ClassificationStatus.UNSUPPORTED,
            reason="BODY_TYPE_OUTSIDE_SUPPORTED_SCOPE",
            body_type=values.body_type,
        )

    body_family = _body_family(values.body_type)
    class_family = _vehicle_family(values.vehicle_class)
    if class_family is not None and body_family != class_family:
        compatible = {body_family, class_family} == {"PASSENGER", "VAN"}
        if not compatible:
            return _result(
                ClassificationStatus.MANUAL_REVIEW,
                reason="CONFLICTING_BODY_TYPE_AND_VEHICLE_CLASS",
                body_type=values.body_type,
                vehicle_class=values.vehicle_class,
            )

    if body_family == "TRUCK":
        return _classify_truck(values)
    if body_family == "PICKUP":
        return _classify_pickup(values)

    seat_result = _seat_classification(values)
    if isinstance(seat_result, VehicleClassificationResult):
        return seat_result
    if body_family == "VAN":
        return _classify_van(values, seat_result)
    if seat_result == "8702":
        if values.body_type == "MPV":
            return _result(
                ClassificationStatus.CLASSIFIED,
                heading="8702",
                rule_code="MPV_AT_LEAST_10_SEATS",
            )
        return _result(
            ClassificationStatus.MANUAL_REVIEW,
            reason="PASSENGER_BODY_CONFLICTS_WITH_AT_LEAST_10_SEATS",
            body_type=values.body_type,
        )
    return _result(
        ClassificationStatus.CLASSIFIED,
        heading="8703",
        rule_code="PASSENGER_VEHICLE_UP_TO_9_SEATS",
    )
