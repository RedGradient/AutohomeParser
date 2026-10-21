from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .types import ClassificationStatus


CLASSIFICATION_RULES_VERSION = "RU-EAEU-VEHICLE-CLASSIFICATION-2026-10-21-v4"
PICKUP_CLASSIFICATION_SOURCE = "https://adilet.zan.kz/rus/docs/H11T0000751"
PICKUP_DRIVER_MASS_KG = 75
PICKUP_PASSENGER_MASS_KG = 68

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
    axle_count: int | None = None
    seat_count_min: int | None = None
    seat_count_max: int | None = None
    gross_mass_kg: int | None = None
    curb_mass_kg: int | None = None
    curb_mass_kg_min: int | None = None
    curb_mass_kg_max: int | None = None
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


def _with_conflict_resolution(
    result: VehicleClassificationResult,
    resolution: str | None,
    *,
    body_type: str,
    vehicle_class: str,
) -> VehicleClassificationResult:
    if resolution is None:
        return result
    return VehicleClassificationResult(
        status=result.status,
        tnved_heading=result.tnved_heading,
        rule_code=result.rule_code,
        missing_fields=result.missing_fields,
        details={
            **result.details,
            "family_conflict_resolution": resolution,
            "body_type": body_type,
            "vehicle_class": vehicle_class,
        },
        rules_version=result.rules_version,
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
    """Классифицировать пикап по Решению КТС от 16.08.2011 № 751."""
    source = PICKUP_CLASSIFICATION_SOURCE
    if values.axle_count is not None and values.axle_count > 2:
        return _result(
            ClassificationStatus.CLASSIFIED,
            heading="8704",
            rule_code="PICKUP_MORE_THAN_TWO_AXLES",
            source=source,
            axle_count=values.axle_count,
        )
    if values.gross_mass_kg is not None and values.gross_mass_kg > 3500:
        return _result(
            ClassificationStatus.CLASSIFIED,
            heading="8704",
            rule_code="PICKUP_GROSS_MASS_OVER_3500",
            source=source,
            gross_mass_kg=values.gross_mass_kg,
        )

    invalid: list[str] = []
    ambiguous: list[str] = []

    if values.axle_count is not None and values.axle_count < 2:
        invalid.append("axle_count")
    if values.gross_mass_kg is not None and values.gross_mass_kg <= 0:
        invalid.append("gross_mass_kg")

    cargo_fields = (
        values.cargo_length_min_mm,
        values.cargo_length_max_mm,
        values.wheelbase_mm,
    )
    if all(value is not None for value in cargo_fields):
        cargo_min = values.cargo_length_min_mm
        cargo_max = values.cargo_length_max_mm
        wheelbase = values.wheelbase_mm
        assert cargo_min is not None and cargo_max is not None
        assert wheelbase is not None
        if cargo_min <= 0 or cargo_max < cargo_min or wheelbase <= 0:
            invalid.extend(
                [
                    "cargo_length_min_mm",
                    "cargo_length_max_mm",
                    "wheelbase_mm",
                ]
            )
        elif cargo_min * 2 > wheelbase:
            return _result(
                ClassificationStatus.CLASSIFIED,
                heading="8704",
                rule_code="PICKUP_CARGO_BED_OVER_HALF_WHEELBASE",
                source=source,
                formula="cargo_length_min_mm * 2 > wheelbase_mm",
                cargo_length_min_mm=cargo_min,
                cargo_length_max_mm=cargo_max,
                wheelbase_mm=wheelbase,
            )
        elif cargo_max * 2 > wheelbase:
            ambiguous.append("cargo_length_mm")

    curb_mass_min = (
        values.curb_mass_kg
        if values.curb_mass_kg is not None
        else values.curb_mass_kg_min
    )
    curb_mass_max = (
        values.curb_mass_kg
        if values.curb_mass_kg is not None
        else values.curb_mass_kg_max
    )
    mass_fields = (
        values.gross_mass_kg,
        curb_mass_min,
        curb_mass_max,
        values.seat_count_min,
        values.seat_count_max,
    )
    if all(value is not None for value in mass_fields):
        gross_mass = values.gross_mass_kg
        seat_min = values.seat_count_min
        seat_max = values.seat_count_max
        assert gross_mass is not None
        assert curb_mass_min is not None and curb_mass_max is not None
        assert seat_min is not None and seat_max is not None
        if (
            curb_mass_min <= 0
            or curb_mass_max < curb_mass_min
            or gross_mass <= curb_mass_max
            or seat_min <= 0
            or seat_max < seat_min
        ):
            invalid.extend(
                [
                    "gross_mass_kg",
                    "curb_mass_kg",
                    "seat_count_min",
                    "seat_count_max",
                ]
            )
        else:
            # В Решении № 751 масса M включает водителя массой 75 кг.
            def goods_capacity_exceeds_passenger_capacity(
                curb_mass: int,
                seats: int,
            ) -> bool:
                passengers = max(seats - 1, 0)
                passenger_mass = passengers * PICKUP_PASSENGER_MASS_KG
                decision_curb_mass = curb_mass + PICKUP_DRIVER_MASS_KG
                return (
                    gross_mass - (decision_curb_mass + passenger_mass)
                    > passenger_mass
                )

            outcomes = {
                goods_capacity_exceeds_passenger_capacity(curb_mass, seats)
                for curb_mass in {curb_mass_min, curb_mass_max}
                for seats in {seat_min, seat_max}
            }
            if outcomes == {True}:
                passengers = max(seat_max - 1, 0)
                return _result(
                    ClassificationStatus.CLASSIFIED,
                    heading="8704",
                    rule_code="PICKUP_GOODS_CAPACITY_EXCEEDS_PASSENGER_CAPACITY",
                    source=source,
                    formula="P - (M + N * 68) > N * 68",
                    gross_mass_kg=gross_mass,
                    source_curb_mass_kg_min=curb_mass_min,
                    source_curb_mass_kg_max=curb_mass_max,
                    decision_curb_mass_kg_min=(
                        curb_mass_min + PICKUP_DRIVER_MASS_KG
                    ),
                    decision_curb_mass_kg_max=(
                        curb_mass_max + PICKUP_DRIVER_MASS_KG
                    ),
                    **(
                        {
                            "source_curb_mass_kg": curb_mass_min,
                            "decision_curb_mass_kg": (
                                curb_mass_min + PICKUP_DRIVER_MASS_KG
                            ),
                        }
                        if curb_mass_min == curb_mass_max
                        else {}
                    ),
                    passenger_seat_count=passengers,
                    passenger_mass_kg=passengers * PICKUP_PASSENGER_MASS_KG,
                )
            if len(outcomes) > 1:
                ambiguous.append("curb_mass_or_seat_count")

    if invalid:
        return _result(
            ClassificationStatus.AMBIGUOUS,
            reason="INVALID_PICKUP_CLASSIFICATION_VALUES",
            source=source,
            invalid_fields=sorted(set(invalid)),
        )
    if ambiguous:
        return _result(
            ClassificationStatus.AMBIGUOUS,
            reason="PICKUP_VARIANTS_CROSS_8703_8704_BOUNDARY",
            source=source,
            ambiguous_fields=sorted(set(ambiguous)),
        )

    required = (
        "axle_count",
        "gross_mass_kg",
        "seat_count_min",
        "seat_count_max",
        "wheelbase_mm",
        "cargo_length_min_mm",
        "cargo_length_max_mm",
    )
    missing = [name for name in required if getattr(values, name) is None]
    if curb_mass_min is None or curb_mass_max is None:
        missing.append("curb_mass_kg")
    if missing:
        return _result(
            ClassificationStatus.MISSING_DATA,
            missing_fields=missing,
            reason="PICKUP_CLASSIFICATION_FEATURES_REQUIRED",
            source=source,
        )
    return _result(
        ClassificationStatus.CLASSIFIED,
        heading="8703",
        rule_code="PICKUP_751_OTHERWISE_8703",
        source=source,
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
    conflict_resolution = None
    if class_family is not None and body_family != class_family:
        compatible = {body_family, class_family} == {"PASSENGER", "VAN"}
        if compatible:
            pass
        elif body_family == "TRUCK" and class_family == "VAN":
            if values.seat_count_min is None or values.seat_count_max is None:
                return _result(
                    ClassificationStatus.MISSING_DATA,
                    missing_fields=[
                        name
                        for name in ("seat_count_min", "seat_count_max")
                        if getattr(values, name) is None
                    ],
                    reason="TRUCK_VAN_CONFLICT_REQUIRES_SEAT_COUNT",
                    body_type=values.body_type,
                    vehicle_class=values.vehicle_class,
                )
            if values.seat_count_min < 10 <= values.seat_count_max:
                return _result(
                    ClassificationStatus.AMBIGUOUS,
                    reason="TRUCK_VAN_CONFLICT_CROSSES_8702_BOUNDARY",
                    body_type=values.body_type,
                    vehicle_class=values.vehicle_class,
                    seat_count_min=values.seat_count_min,
                    seat_count_max=values.seat_count_max,
                )
            if values.seat_count_min >= 10:
                return _result(
                    ClassificationStatus.MANUAL_REVIEW,
                    reason="TRUCK_BODY_CONFLICTS_WITH_PASSENGER_SEAT_COUNT",
                    body_type=values.body_type,
                    vehicle_class=values.vehicle_class,
                    seat_count_min=values.seat_count_min,
                    seat_count_max=values.seat_count_max,
                )
            conflict_resolution = "SPECIFIC_TRUCK_BODY_OVERRIDES_VAN_CLASS"
        elif (
            body_family == "TRUCK"
            and class_family == "PASSENGER"
            and (
                values.vehicle_class == "MPV"
                or values.vehicle_class.endswith("_MPV")
            )
            and values.seat_count_min is not None
            and values.seat_count_max is not None
            and values.seat_count_max <= 2
        ):
            conflict_resolution = (
                "TWO_SEAT_COMMERCIAL_TRUCK_BODY_OVERRIDES_MPV_CLASS"
            )
        elif body_family == "TRUCK" and class_family == "PICKUP":
            body_family = "PICKUP"
            conflict_resolution = "SPECIFIC_PICKUP_CLASS_OVERRIDES_TRUCK_BODY"
        elif body_family == "PICKUP" and class_family in {
            "TRUCK",
            "PASSENGER",
        }:
            conflict_resolution = "SPECIFIC_PICKUP_BODY_OVERRIDES_BROAD_CLASS"
        else:
            return _result(
                ClassificationStatus.MANUAL_REVIEW,
                reason="CONFLICTING_BODY_TYPE_AND_VEHICLE_CLASS",
                body_type=values.body_type,
                vehicle_class=values.vehicle_class,
            )

    if body_family == "TRUCK":
        return _with_conflict_resolution(
            _classify_truck(values),
            conflict_resolution,
            body_type=values.body_type,
            vehicle_class=values.vehicle_class,
        )
    if body_family == "PICKUP":
        return _with_conflict_resolution(
            _classify_pickup(values),
            conflict_resolution,
            body_type=values.body_type,
            vehicle_class=values.vehicle_class,
        )

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
