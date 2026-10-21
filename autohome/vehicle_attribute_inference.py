from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Any, Iterable, Mapping

from autohome.import_duty.classifier import (
    VehicleClassificationInput,
    classify_vehicle,
)
from autohome.import_duty.types import ClassificationStatus


VEHICLE_ATTRIBUTE_INFERENCE_RULES_VERSION = "RU-EAEU-VEHICLE-INFERENCE-2026-10-21-v5"
INFERRED_INPUTS_USED = "INFERRED_INPUTS_USED"
TRUCK_OCCUPANT_MASS_KG = 65
INFERRED_MASS_CATEGORY_GUARD_KG = 100
TRUCK_GROSS_MASS_NAME_RE = re.compile(
    r"(?<![\d.])(?P<tonnes>\d{1,2}(?:\.\d+)?)吨(?=(?:底盘|级|加|\s|$))"
)


class VehiclePurposeType(StrEnum):
    """Нормализованное назначение транспортного средства."""

    FIRE_FIGHTING = "FIRE_FIGHTING"
    BREAKDOWN = "BREAKDOWN"
    MOBILE_CRANE = "MOBILE_CRANE"
    CONCRETE_MIXER = "CONCRETE_MIXER"
    ROAD_SWEEPER = "ROAD_SWEEPER"
    SPRINKLER = "SPRINKLER"
    AERIAL_PLATFORM = "AERIAL_PLATFORM"
    AMBULANCE = "AMBULANCE"
    MOTORHOME = "MOTORHOME"
    REFUSE_TRUCK = "REFUSE_TRUCK"
    UNKNOWN_SPECIAL = "UNKNOWN_SPECIAL"


class VehicleTechnicalCategory(StrEnum):
    """Техническая категория колёсного транспортного средства."""

    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    N1 = "N1"
    N2 = "N2"
    N3 = "N3"


class InferenceConfidence(StrEnum):
    """Уровень надёжности косвенного вывода."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class ParameterMatchType(StrEnum):
    """Способ проверки сырого значения параметра Autohome."""

    DIRECT_PRESENT = "DIRECT_PRESENT"
    SUBITEM_AVAILABLE = "SUBITEM_AVAILABLE"
    REAR_ELECTRIC_WINDOWS = "REAR_ELECTRIC_WINDOWS"
    SEAT_LAYOUT = "SEAT_LAYOUT"


@dataclass(frozen=True)
class RawParameter:
    """Исходное китайское определение и значение параметра комплектации."""

    name: str
    raw_value: Mapping[str, Any]


@dataclass(frozen=True)
class ParameterInferenceRule:
    """Одно положительное правило вывода конструктивного признака."""

    raw_name: str
    target_field: str
    rule_code: str
    match_type: ParameterMatchType
    confidence: InferenceConfidence = InferenceConfidence.HIGH
    body_types: frozenset[str] | None = None


@dataclass(frozen=True)
class PurposeMarkerRule:
    """Правило нормализации назначения по сырому названию автомобиля."""

    markers: tuple[str, ...]
    purpose_type: VehiclePurposeType
    rule_code: str
    confidence: InferenceConfidence = InferenceConfidence.HIGH
    excluded_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class InferenceEvidence:
    """Воспроизводимое свидетельство, на котором основан вывод."""

    source: str
    marker: str
    raw_value: Any


@dataclass(frozen=True)
class InferenceDecision:
    """Выведенное значение одного нормализованного поля."""

    value: bool | int | VehiclePurposeType | VehicleTechnicalCategory
    rule_code: str
    confidence: InferenceConfidence
    evidence: tuple[InferenceEvidence, ...]


@dataclass(frozen=True)
class VehicleAttributeInferenceResult:
    """Результат косвенного вывода без изменения исходных данных."""

    decisions: dict[str, InferenceDecision] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    rules_version: str = VEHICLE_ATTRIBUTE_INFERENCE_RULES_VERSION

    def value(
        self, field_name: str
    ) -> bool | int | VehiclePurposeType | VehicleTechnicalCategory | None:
        decision = self.decisions.get(field_name)
        return decision.value if decision is not None else None


INFERRED_STORAGE_FIELDS = frozenset(
    {
        "has_permanent_rear_seats",
        "has_rear_side_windows",
        "has_rear_windowed_door",
        "has_separate_cargo_compartment",
        "is_special_purpose",
        "vehicle_purpose_type",
        "vehicle_technical_category",
        "gross_mass_kg",
    }
)


TAILGATE_BODY_TYPES = frozenset(
    {
        "HATCHBACK",
        "LIFTBACK",
        "WAGON",
        "CROSSOVER_WAGON",
        "SUV",
        "MPV",
        "VAN",
    }
)
CARGO_BOX_BODY_TYPES = frozenset({"PICKUP", "TRUCK"})
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
PASSENGER_CLASS_SUFFIXES = ("_CAR", "_SUV", "_MPV")
PASSENGER_CLASSES = frozenset({"MPV"})
VAN_CLASSES = frozenset({"MICROVAN", "LIGHT_COMMERCIAL_VAN"})
PICKUP_CLASSES = frozenset({"PICKUP", "PREMIUM_PICKUP"})
TRUCK_CLASSES = frozenset({"MINI_TRUCK", "LIGHT_TRUCK"})
GOODS_TRANSPORT_MARKERS = (
    "载货",
    "运输车",
    "厢式货车",
    "栏板",
    "仓栅",
)


PARAMETER_INFERENCE_RULES = (
    ParameterInferenceRule(
        "后排座椅放倒形式",
        "has_permanent_rear_seats",
        "REAR_SEAT_FOLDING_PRESENT",
        ParameterMatchType.SUBITEM_AVAILABLE,
    ),
    ParameterInferenceRule(
        "第二排座椅调节",
        "has_permanent_rear_seats",
        "SECOND_ROW_SEAT_ADJUSTMENT_PRESENT",
        ParameterMatchType.SUBITEM_AVAILABLE,
    ),
    ParameterInferenceRule(
        "座椅布局",
        "has_permanent_rear_seats",
        "MULTI_ROW_SEAT_LAYOUT_PRESENT",
        ParameterMatchType.SEAT_LAYOUT,
    ),
    ParameterInferenceRule(
        "第二排座椅电动调节",
        "has_permanent_rear_seats",
        "SECOND_ROW_POWER_SEAT_OPTION_PRESENT",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "第二排独立座椅",
        "has_permanent_rear_seats",
        "SECOND_ROW_INDIVIDUAL_SEATS_PRESENT",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "后排座椅电动放倒",
        "has_permanent_rear_seats",
        "REAR_POWER_FOLDING_OPTION_PRESENT",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "第三排座椅调节",
        "has_permanent_rear_seats",
        "THIRD_ROW_SEAT_ADJUSTMENT_PRESENT",
        ParameterMatchType.SUBITEM_AVAILABLE,
    ),
    ParameterInferenceRule(
        "第三排座椅电动调节",
        "has_permanent_rear_seats",
        "THIRD_ROW_POWER_SEAT_OPTION_PRESENT",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "前/后电动车窗",
        "has_rear_side_windows",
        "REAR_POWER_WINDOWS_PRESENT_OR_AVAILABLE",
        ParameterMatchType.REAR_ELECTRIC_WINDOWS,
    ),
    ParameterInferenceRule(
        "后排侧隐私玻璃",
        "has_rear_side_windows",
        "REAR_PRIVACY_GLASS_PRESENT_OR_AVAILABLE",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "后排侧窗遮阳帘",
        "has_rear_side_windows",
        "REAR_SIDE_WINDOW_CURTAIN_PRESENT_OR_AVAILABLE",
        ParameterMatchType.SUBITEM_AVAILABLE,
    ),
    ParameterInferenceRule(
        "后排调光隐私玻璃",
        "has_rear_side_windows",
        "REAR_DIMMING_GLASS_PRESENT_OR_AVAILABLE",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "尾门玻璃独立开启",
        "has_rear_windowed_door",
        "TAILGATE_GLASS_OPENING_PRESENT_OR_AVAILABLE",
        ParameterMatchType.DIRECT_PRESENT,
    ),
    ParameterInferenceRule(
        "后雨刷",
        "has_rear_windowed_door",
        "REAR_WIPER_WITH_TAILGATE_BODY",
        ParameterMatchType.DIRECT_PRESENT,
        confidence=InferenceConfidence.MEDIUM,
        body_types=TAILGATE_BODY_TYPES,
    ),
    ParameterInferenceRule(
        "货箱尺寸(mm)",
        "has_separate_cargo_compartment",
        "CARGO_BOX_DIMENSIONS_WITH_GOODS_BODY",
        ParameterMatchType.DIRECT_PRESENT,
        body_types=CARGO_BOX_BODY_TYPES,
    ),
)


PURPOSE_MARKER_RULES = (
    PurposeMarkerRule(
        ("混凝土搅拌", "搅拌车"),
        VehiclePurposeType.CONCRETE_MIXER,
        "PURPOSE_CONCRETE_MIXER_BY_NAME",
    ),
    PurposeMarkerRule(
        ("高空作业",),
        VehiclePurposeType.AERIAL_PLATFORM,
        "PURPOSE_AERIAL_PLATFORM_BY_NAME",
    ),
    PurposeMarkerRule(
        ("消防",),
        VehiclePurposeType.FIRE_FIGHTING,
        "PURPOSE_FIRE_FIGHTING_BY_NAME",
    ),
    PurposeMarkerRule(
        ("清障",),
        VehiclePurposeType.BREAKDOWN,
        "PURPOSE_BREAKDOWN_BY_NAME",
        confidence=InferenceConfidence.MEDIUM,
    ),
    PurposeMarkerRule(
        ("扫路",),
        VehiclePurposeType.ROAD_SWEEPER,
        "PURPOSE_ROAD_SWEEPER_BY_NAME",
    ),
    PurposeMarkerRule(
        ("洒水",),
        VehiclePurposeType.SPRINKLER,
        "PURPOSE_SPRINKLER_BY_NAME",
    ),
    PurposeMarkerRule(
        ("起重", "吊车"),
        VehiclePurposeType.MOBILE_CRANE,
        "PURPOSE_MOBILE_CRANE_BY_NAME",
        confidence=InferenceConfidence.MEDIUM,
        excluded_markers=("随车起重", "随车吊"),
    ),
    PurposeMarkerRule(
        ("救护",),
        VehiclePurposeType.AMBULANCE,
        "PURPOSE_AMBULANCE_BY_NAME",
    ),
    PurposeMarkerRule(
        ("旅居车", "房车"),
        VehiclePurposeType.MOTORHOME,
        "PURPOSE_MOTORHOME_BY_NAME",
    ),
    PurposeMarkerRule(
        ("垃圾",),
        VehiclePurposeType.REFUSE_TRUCK,
        "PURPOSE_REFUSE_TRUCK_BY_NAME",
    ),
    PurposeMarkerRule(
        ("环卫", "专用车"),
        VehiclePurposeType.UNKNOWN_SPECIAL,
        "PURPOSE_GENERIC_SPECIAL_MARKER",
        confidence=InferenceConfidence.MEDIUM,
    ),
)


EAEU_8705_PURPOSE_TYPES = frozenset(
    {
        VehiclePurposeType.FIRE_FIGHTING,
        VehiclePurposeType.BREAKDOWN,
        VehiclePurposeType.MOBILE_CRANE,
        VehiclePurposeType.CONCRETE_MIXER,
        VehiclePurposeType.ROAD_SWEEPER,
        VehiclePurposeType.SPRINKLER,
        VehiclePurposeType.AERIAL_PLATFORM,
    }
)
KNOWN_NON_8705_PURPOSE_TYPES = frozenset(
    {
        VehiclePurposeType.AMBULANCE,
        VehiclePurposeType.MOTORHOME,
        VehiclePurposeType.REFUSE_TRUCK,
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _direct_present(raw_value: Mapping[str, Any]) -> bool:
    return _text(raw_value.get("itemname")) not in {"", "-"}


def _available_subitems(raw_value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    subitems = raw_value.get("sublist")
    if not isinstance(subitems, list):
        return []
    return [
        item
        for item in subitems
        if isinstance(item, Mapping) and _text(item.get("value")) in {"●", "○"}
    ]


def parameter_matches(
    rule: ParameterInferenceRule,
    raw_value: Mapping[str, Any],
    *,
    body_type: str | None,
) -> bool:
    """Проверить одно правило по исходному значению без изменения данных."""
    if rule.body_types is not None and body_type not in rule.body_types:
        return False
    if rule.match_type == ParameterMatchType.DIRECT_PRESENT:
        return _direct_present(raw_value)
    if rule.match_type == ParameterMatchType.SUBITEM_AVAILABLE:
        return bool(_available_subitems(raw_value))
    if rule.match_type == ParameterMatchType.REAR_ELECTRIC_WINDOWS:
        return re.search(r"后[●○]", _text(raw_value.get("itemname"))) is not None
    if rule.match_type == ParameterMatchType.SEAT_LAYOUT:
        subitems = raw_value.get("sublist")
        if not isinstance(subitems, list):
            return False
        return any(
            isinstance(item, Mapping)
            and _text(item.get("value")) == "●"
            and len(re.findall(r"\d+", _text(item.get("name")))) >= 2
            for item in subitems
        )
    raise ValueError(f"Неизвестный способ сопоставления: {rule.match_type}")


def _parameter_evidence(
    parameter: RawParameter,
    rule: ParameterInferenceRule,
) -> InferenceEvidence:
    subitems = _available_subitems(parameter.raw_value)
    raw_value: Any = parameter.raw_value.get("itemname")
    if subitems:
        raw_value = [
            {"name": item.get("name"), "value": item.get("value")}
            for item in subitems
        ]
    return InferenceEvidence(
        source="spec_parameters.raw_json",
        marker=parameter.name,
        raw_value=raw_value,
    )


def infer_parameter_attributes(
    parameters: Iterable[RawParameter],
    *,
    body_type: str | None,
) -> dict[str, InferenceDecision]:
    """Вывести положительные конструктивные признаки из сырых параметров."""
    rules_by_name: dict[str, list[ParameterInferenceRule]] = {}
    rule_priority = {
        rule: position for position, rule in enumerate(PARAMETER_INFERENCE_RULES)
    }
    for rule in PARAMETER_INFERENCE_RULES:
        rules_by_name.setdefault(rule.raw_name, []).append(rule)

    matches: dict[str, list[tuple[ParameterInferenceRule, InferenceEvidence]]] = {}
    for parameter in parameters:
        for rule in rules_by_name.get(parameter.name, ()):
            if parameter_matches(rule, parameter.raw_value, body_type=body_type):
                matches.setdefault(rule.target_field, []).append(
                    (rule, _parameter_evidence(parameter, rule))
                )

    decisions = {}
    for field_name, field_matches in matches.items():
        field_matches.sort(key=lambda item: rule_priority[item[0]])
        primary_rule = field_matches[0][0]
        confidence = (
            InferenceConfidence.HIGH
            if any(rule.confidence == InferenceConfidence.HIGH for rule, _ in field_matches)
            else InferenceConfidence.MEDIUM
        )
        decisions[field_name] = InferenceDecision(
            value=True,
            rule_code=primary_rule.rule_code,
            confidence=confidence,
            evidence=tuple(evidence for _, evidence in field_matches),
        )
    return decisions


def infer_vehicle_purpose(
    *,
    spec_name: str | None,
    series_name: str | None,
) -> tuple[InferenceDecision | None, tuple[str, ...]]:
    """Определить назначение по исходным китайским названиям."""
    sources = (
        ("specs.raw_json.name", _text(spec_name)),
        ("series.raw_json.name", _text(series_name)),
    )
    matches: list[tuple[PurposeMarkerRule, InferenceEvidence]] = []
    for rule in PURPOSE_MARKER_RULES:
        for source, raw_name in sources:
            if not raw_name or any(marker in raw_name for marker in rule.excluded_markers):
                continue
            marker = next((item for item in rule.markers if item in raw_name), None)
            if marker is not None:
                matches.append(
                    (
                        rule,
                        InferenceEvidence(
                            source=source,
                            marker=marker,
                            raw_value=raw_name,
                        ),
                    )
                )

    if not matches:
        return None, ()
    concrete_matches = [
        item
        for item in matches
        if item[0].purpose_type != VehiclePurposeType.UNKNOWN_SPECIAL
    ]
    if concrete_matches:
        matches = concrete_matches
    purposes = {rule.purpose_type for rule, _ in matches}
    if len(purposes) > 1:
        return (
            InferenceDecision(
                value=VehiclePurposeType.UNKNOWN_SPECIAL,
                rule_code="PURPOSE_MARKER_CONFLICT",
                confidence=InferenceConfidence.MEDIUM,
                evidence=tuple(evidence for _, evidence in matches),
            ),
            ("CONFLICTING_PURPOSE_MARKERS",),
        )
    primary_rule = matches[0][0]
    confidence = (
        InferenceConfidence.HIGH
        if any(rule.confidence == InferenceConfidence.HIGH for rule, _ in matches)
        else InferenceConfidence.MEDIUM
    )
    return (
        InferenceDecision(
            value=primary_rule.purpose_type,
            rule_code=primary_rule.rule_code,
            confidence=confidence,
            evidence=tuple(evidence for _, evidence in matches),
        ),
        (),
    )


def special_purpose_value(purpose_type: VehiclePurposeType) -> bool | None:
    """Преобразовать назначение в признак позиции 8705."""
    if purpose_type in EAEU_8705_PURPOSE_TYPES:
        return True
    if purpose_type in KNOWN_NON_8705_PURPOSE_TYPES:
        return False
    return None


def _normalized_evidence(field_name: str, value: Any) -> InferenceEvidence:
    return InferenceEvidence(
        source="spec_vehicle_attributes",
        marker=field_name,
        raw_value=value,
    )


def _attribute_evidence(
    field_name: str,
    value: bool,
    inferred_attributes: Mapping[str, InferenceDecision],
) -> tuple[InferenceEvidence, ...]:
    decision = inferred_attributes.get(field_name)
    if decision is not None and decision.value is value:
        return decision.evidence
    return (_normalized_evidence(field_name, value),)


def _name_marker_evidence(
    marker: str,
    *,
    spec_name: str | None,
    series_name: str | None,
) -> tuple[InferenceEvidence, ...]:
    evidence = []
    for source, raw_name in (
        ("specs.raw_json.name", _text(spec_name)),
        ("series.raw_json.name", _text(series_name)),
    ):
        if marker in raw_name:
            evidence.append(
                InferenceEvidence(source=source, marker=marker, raw_value=raw_name)
            )
    return tuple(evidence)


def _is_passenger_class(vehicle_class: str | None) -> bool:
    return bool(
        vehicle_class
        and (
            vehicle_class in PASSENGER_CLASSES
            or vehicle_class.endswith(PASSENGER_CLASS_SUFFIXES)
        )
    )


def infer_ordinary_transport(
    *,
    body_type: str | None,
    vehicle_class: str | None,
    seat_count_min: int | None,
    seat_count_max: int | None,
    gross_mass_kg: int | None,
    payload_kg_min: int | None,
    payload_kg_max: int | None,
    cargo_length_min_mm: int | None,
    cargo_width_min_mm: int | None,
    cargo_height_min_mm: int | None,
    has_permanent_rear_seats: bool | None,
    has_rear_side_windows: bool | None,
    has_rear_windowed_door: bool | None,
    has_separate_cargo_compartment: bool | None,
    spec_name: str | None,
    series_name: str | None,
    inferred_attributes: Mapping[str, InferenceDecision],
) -> InferenceDecision | None:
    """Подтвердить обычную перевозку людей или грузов положительными данными."""
    seats_are_valid = (
        seat_count_min is not None
        and seat_count_max is not None
        and 1 <= seat_count_min <= seat_count_max
    )
    if (
        body_type in PASSENGER_BODY_TYPES
        and _is_passenger_class(vehicle_class)
        and seats_are_valid
    ):
        return InferenceDecision(
            value=False,
            rule_code="ORDINARY_PASSENGER_BODY_CLASS_AND_SEATS",
            confidence=InferenceConfidence.HIGH,
            evidence=(
                _normalized_evidence("body_type", body_type),
                _normalized_evidence("vehicle_class", vehicle_class),
                _normalized_evidence("seat_count_min", seat_count_min),
                _normalized_evidence("seat_count_max", seat_count_max),
            ),
        )

    if body_type == "VAN" and vehicle_class in VAN_CLASSES:
        if seats_are_valid and seat_count_min >= 10:
            return InferenceDecision(
                value=False,
                rule_code="ORDINARY_PASSENGER_VAN_AT_LEAST_10_SEATS",
                confidence=InferenceConfidence.HIGH,
                evidence=(
                    _normalized_evidence("body_type", body_type),
                    _normalized_evidence("vehicle_class", vehicle_class),
                    _normalized_evidence("seat_count_min", seat_count_min),
                    _normalized_evidence("seat_count_max", seat_count_max),
                ),
            )
        if (
            has_permanent_rear_seats is True
            and has_rear_side_windows is True
        ):
            return InferenceDecision(
                value=False,
                rule_code="ORDINARY_PASSENGER_VAN_BY_CONSTRUCTION",
                confidence=InferenceConfidence.HIGH,
                evidence=(
                    *_attribute_evidence(
                        "has_permanent_rear_seats",
                        True,
                        inferred_attributes,
                    ),
                    *_attribute_evidence(
                        "has_rear_side_windows",
                        True,
                        inferred_attributes,
                    ),
                ),
            )

        return InferenceDecision(
            value=False,
            rule_code="ORDINARY_VAN_BODY_AND_TRANSPORT_CLASS",
            confidence=InferenceConfidence.MEDIUM,
            evidence=(
                _normalized_evidence("body_type", body_type),
                _normalized_evidence("vehicle_class", vehicle_class),
            ),
        )

    truck_transport_classes = TRUCK_CLASSES | VAN_CLASSES | PICKUP_CLASSES
    body_and_class_are_goods = (
        body_type == "PICKUP" and vehicle_class in PICKUP_CLASSES
    ) or (body_type == "TRUCK" and vehicle_class in truck_transport_classes)
    if not body_and_class_are_goods:
        return None

    for marker in GOODS_TRANSPORT_MARKERS:
        name_evidence = _name_marker_evidence(
            marker,
            spec_name=spec_name,
            series_name=series_name,
        )
        if name_evidence:
            return InferenceDecision(
                value=False,
                rule_code="ORDINARY_GOODS_TRANSPORT_BY_NAME",
                confidence=InferenceConfidence.HIGH,
                evidence=(
                    _normalized_evidence("body_type", body_type),
                    _normalized_evidence("vehicle_class", vehicle_class),
                    *name_evidence,
                ),
            )

    cargo_dimensions_present = all(
        value is not None and value > 0
        for value in (
            cargo_length_min_mm,
            cargo_width_min_mm,
            cargo_height_min_mm,
        )
    )
    payload_present = any(
        value is not None and value > 0
        for value in (payload_kg_min, payload_kg_max)
    )
    if (
        cargo_dimensions_present
        and payload_present
        and gross_mass_kg is not None
        and gross_mass_kg > 0
    ):
        evidence = [
            _normalized_evidence("body_type", body_type),
            _normalized_evidence("vehicle_class", vehicle_class),
            _normalized_evidence("gross_mass_kg", gross_mass_kg),
            _normalized_evidence("cargo_length_min_mm", cargo_length_min_mm),
            _normalized_evidence("cargo_width_min_mm", cargo_width_min_mm),
            _normalized_evidence("cargo_height_min_mm", cargo_height_min_mm),
        ]
        if payload_kg_min is not None:
            evidence.append(_normalized_evidence("payload_kg_min", payload_kg_min))
        if payload_kg_max is not None:
            evidence.append(_normalized_evidence("payload_kg_max", payload_kg_max))
        if has_separate_cargo_compartment is True:
            evidence.append(
                _normalized_evidence("has_separate_cargo_compartment", True)
            )
        return InferenceDecision(
            value=False,
            rule_code="ORDINARY_GOODS_BODY_CLASS_CARGO_AND_PAYLOAD",
            confidence=InferenceConfidence.HIGH,
            evidence=tuple(evidence),
        )
    if body_type == "PICKUP":
        return InferenceDecision(
            value=False,
            rule_code="ORDINARY_PICKUP_BODY_AND_CLASS",
            confidence=InferenceConfidence.HIGH,
            evidence=(
                _normalized_evidence("body_type", body_type),
                _normalized_evidence("vehicle_class", vehicle_class),
            ),
        )
    if cargo_dimensions_present:
        return InferenceDecision(
            value=False,
            rule_code="ORDINARY_TRUCK_WITH_CARGO_BOX",
            confidence=InferenceConfidence.HIGH,
            evidence=(
                _normalized_evidence("body_type", body_type),
                _normalized_evidence("vehicle_class", vehicle_class),
                _normalized_evidence("cargo_length_min_mm", cargo_length_min_mm),
                _normalized_evidence("cargo_width_min_mm", cargo_width_min_mm),
                _normalized_evidence("cargo_height_min_mm", cargo_height_min_mm),
            ),
        )
    if body_type == "TRUCK":
        return InferenceDecision(
            value=False,
            rule_code="ORDINARY_TRUCK_BODY_AND_TRANSPORT_CLASS",
            confidence=InferenceConfidence.MEDIUM,
            evidence=(
                _normalized_evidence("body_type", body_type),
                _normalized_evidence("vehicle_class", vehicle_class),
            ),
        )
    return None


def infer_commercial_gross_mass(
    *,
    body_type: str | None,
    gross_mass_kg: int | None,
    curb_mass_kg: int | None,
    payload_kg_min: int | None,
    payload_kg_max: int | None,
    seat_count_min: int | None,
    seat_count_max: int | None,
    spec_name: str | None,
) -> InferenceDecision | None:
    """Восстановить полную массу грузовика или пикапа по точным компонентам."""
    if body_type not in {"TRUCK", "PICKUP"} or gross_mass_kg is not None:
        return None

    if body_type == "TRUCK":
        raw_name = _text(spec_name)
        name_match = TRUCK_GROSS_MASS_NAME_RE.search(raw_name)
        if name_match is not None:
            try:
                mass = Decimal(name_match.group("tonnes")) * 1000
            except InvalidOperation:
                mass = Decimal(0)
            if 500 <= mass <= 100_000 and mass == mass.to_integral_value():
                return InferenceDecision(
                    value=int(mass),
                    rule_code="TRUCK_GROSS_MASS_FROM_SPEC_NAME",
                    confidence=InferenceConfidence.HIGH,
                    evidence=(
                        InferenceEvidence(
                            source="specs.raw_json.name",
                            marker=name_match.group(0),
                            raw_value=raw_name,
                        ),
                    ),
                )

    exact_inputs = (
        curb_mass_kg is not None
        and curb_mass_kg > 0
        and payload_kg_min is not None
        and payload_kg_min > 0
        and payload_kg_min == payload_kg_max
        and seat_count_min is not None
        and seat_count_min > 0
        and seat_count_min == seat_count_max
    )
    if not exact_inputs:
        return None
    assert curb_mass_kg is not None
    assert payload_kg_max is not None
    assert seat_count_max is not None
    inferred_mass = (
        curb_mass_kg
        + payload_kg_max
        + seat_count_max * TRUCK_OCCUPANT_MASS_KG
    )
    return InferenceDecision(
        value=inferred_mass,
        rule_code=(
            "PICKUP_GROSS_MASS_FROM_CURB_PAYLOAD_AND_SEATS"
            if body_type == "PICKUP"
            else "TRUCK_GROSS_MASS_FROM_CURB_PAYLOAD_AND_SEATS"
        ),
        confidence=InferenceConfidence.MEDIUM,
        evidence=(
            _normalized_evidence("curb_mass_kg", curb_mass_kg),
            _normalized_evidence("payload_kg", payload_kg_max),
            _normalized_evidence("seat_count", seat_count_max),
            InferenceEvidence(
                source="inference_formula",
                marker="curb_mass + payload + seats * 65",
                raw_value=inferred_mass,
            ),
        ),
    )


def infer_vehicle_attributes(
    parameters: Iterable[RawParameter],
    *,
    body_type: str | None,
    vehicle_class: str | None = None,
    seat_count_min: int | None = None,
    seat_count_max: int | None = None,
    curb_mass_kg: int | None = None,
    gross_mass_kg: int | None = None,
    payload_kg_min: int | None = None,
    payload_kg_max: int | None = None,
    length_mm: int | None = None,
    wheelbase_mm: int | None = None,
    cargo_length_min_mm: int | None = None,
    cargo_length_max_mm: int | None = None,
    cargo_width_min_mm: int | None = None,
    cargo_width_max_mm: int | None = None,
    cargo_height_min_mm: int | None = None,
    cargo_height_max_mm: int | None = None,
    has_permanent_rear_seats: bool | None = None,
    has_rear_side_windows: bool | None = None,
    has_rear_windowed_door: bool | None = None,
    has_separate_cargo_compartment: bool | None = None,
    is_special_purpose: bool | None = None,
    spec_name: str | None = None,
    series_name: str | None = None,
) -> VehicleAttributeInferenceResult:
    """Выполнить все косвенные правила для одной комплектации."""
    decisions = infer_parameter_attributes(parameters, body_type=body_type)
    inferred_gross_mass = infer_commercial_gross_mass(
        body_type=body_type,
        gross_mass_kg=gross_mass_kg,
        curb_mass_kg=curb_mass_kg,
        payload_kg_min=payload_kg_min,
        payload_kg_max=payload_kg_max,
        seat_count_min=seat_count_min,
        seat_count_max=seat_count_max,
        spec_name=spec_name,
    )
    if inferred_gross_mass is not None:
        decisions["gross_mass_kg"] = inferred_gross_mass
    purpose, warnings = infer_vehicle_purpose(
        spec_name=spec_name,
        series_name=series_name,
    )
    if purpose is not None:
        decisions["vehicle_purpose_type"] = purpose
        assert isinstance(purpose.value, VehiclePurposeType)
        special_value = special_purpose_value(purpose.value)
        if special_value is not None:
            decisions["is_special_purpose"] = InferenceDecision(
                value=special_value,
                rule_code="SPECIAL_PURPOSE_FROM_VEHICLE_PURPOSE",
                confidence=purpose.confidence,
                evidence=purpose.evidence,
            )
    else:
        def stored_or_inferred(
            field_name: str,
            stored_value: bool | None,
        ) -> bool | None:
            if stored_value is not None:
                return stored_value
            decision = decisions.get(field_name)
            if decision is not None and isinstance(decision.value, bool):
                return decision.value
            return None

        ordinary_transport = infer_ordinary_transport(
            body_type=body_type,
            vehicle_class=vehicle_class,
            seat_count_min=seat_count_min,
            seat_count_max=seat_count_max,
            gross_mass_kg=(
                gross_mass_kg
                if gross_mass_kg is not None
                else (
                    int(inferred_gross_mass.value)
                    if inferred_gross_mass is not None
                    else None
                )
            ),
            payload_kg_min=payload_kg_min,
            payload_kg_max=payload_kg_max,
            cargo_length_min_mm=cargo_length_min_mm,
            cargo_width_min_mm=cargo_width_min_mm,
            cargo_height_min_mm=cargo_height_min_mm,
            has_permanent_rear_seats=stored_or_inferred(
                "has_permanent_rear_seats", has_permanent_rear_seats
            ),
            has_rear_side_windows=stored_or_inferred(
                "has_rear_side_windows", has_rear_side_windows
            ),
            has_rear_windowed_door=stored_or_inferred(
                "has_rear_windowed_door", has_rear_windowed_door
            ),
            has_separate_cargo_compartment=stored_or_inferred(
                "has_separate_cargo_compartment",
                has_separate_cargo_compartment,
            ),
            spec_name=spec_name,
            series_name=series_name,
            inferred_attributes=decisions,
        )
        if ordinary_transport is not None:
            decisions["is_special_purpose"] = ordinary_transport

    if (
        "has_permanent_rear_seats" not in decisions
        and seat_count_min is not None
        and seat_count_max is not None
        and 1 <= seat_count_min <= seat_count_max <= 2
    ):
        decisions["has_permanent_rear_seats"] = InferenceDecision(
            value=False,
            rule_code="NO_REAR_SEATS_WITH_AT_MOST_TWO_SEATS",
            confidence=InferenceConfidence.HIGH,
            evidence=(
                _normalized_evidence("seat_count_min", seat_count_min),
                _normalized_evidence("seat_count_max", seat_count_max),
            ),
        )

    if "has_rear_windowed_door" not in decisions and body_type == "SEDAN":
        decisions["has_rear_windowed_door"] = InferenceDecision(
            value=False,
            rule_code="NO_WINDOWED_REAR_DOOR_FOR_SEDAN",
            confidence=InferenceConfidence.HIGH,
            evidence=(_normalized_evidence("body_type", body_type),),
        )

    special_purpose_decision = decisions.get("is_special_purpose")
    ordinary_pickup = (
        body_type == "PICKUP"
        and is_special_purpose is not True
        and special_purpose_decision is not None
        and special_purpose_decision.value is False
        and special_purpose_decision.rule_code.startswith("ORDINARY_")
    )
    if "has_rear_windowed_door" not in decisions and ordinary_pickup:
        decisions["has_rear_windowed_door"] = InferenceDecision(
            value=False,
            rule_code="NO_WINDOWED_REAR_DOOR_FOR_ORDINARY_PICKUP",
            confidence=InferenceConfidence.HIGH,
            evidence=(
                _normalized_evidence("body_type", body_type),
                *special_purpose_decision.evidence,
            ),
        )

    def effective_value(field_name: str, explicit_value: Any) -> Any:
        if explicit_value is not None:
            return explicit_value
        decision = decisions.get(field_name)
        return decision.value if decision is not None else None

    effective_gross_mass = effective_value("gross_mass_kg", gross_mass_kg)
    technical_classification = classify_vehicle(
        VehicleClassificationInput(
            body_type=body_type,
            vehicle_class=vehicle_class,
            seat_count_min=seat_count_min,
            seat_count_max=seat_count_max,
            gross_mass_kg=effective_gross_mass,
            curb_mass_kg=curb_mass_kg,
            payload_kg_min=payload_kg_min,
            payload_kg_max=payload_kg_max,
            length_mm=length_mm,
            wheelbase_mm=wheelbase_mm,
            cargo_length_min_mm=cargo_length_min_mm,
            cargo_length_max_mm=cargo_length_max_mm,
            cargo_width_min_mm=cargo_width_min_mm,
            cargo_width_max_mm=cargo_width_max_mm,
            cargo_height_min_mm=cargo_height_min_mm,
            cargo_height_max_mm=cargo_height_max_mm,
            has_permanent_rear_seats=effective_value(
                "has_permanent_rear_seats", has_permanent_rear_seats
            ),
            has_rear_side_windows=effective_value(
                "has_rear_side_windows", has_rear_side_windows
            ),
            has_rear_windowed_door=effective_value(
                "has_rear_windowed_door", has_rear_windowed_door
            ),
            has_separate_cargo_compartment=effective_value(
                "has_separate_cargo_compartment",
                has_separate_cargo_compartment,
            ),
            is_special_purpose=effective_value(
                "is_special_purpose", is_special_purpose
            ),
        )
    )
    technical_category = None
    inferred_mass_near_category_boundary = (
        body_type == "PICKUP"
        and inferred_gross_mass is not None
        and any(
            abs(int(inferred_gross_mass.value) - boundary)
            <= INFERRED_MASS_CATEGORY_GUARD_KG
            for boundary in (3500, 12000)
        )
    )
    if technical_classification.status == ClassificationStatus.CLASSIFIED:
        if technical_classification.tnved_heading == "8703":
            technical_category = VehicleTechnicalCategory.M1
        elif (
            technical_classification.tnved_heading == "8702"
            and effective_gross_mass is not None
        ):
            technical_category = (
                VehicleTechnicalCategory.M2
                if effective_gross_mass <= 5000
                else VehicleTechnicalCategory.M3
            )
        elif (
            technical_classification.tnved_heading == "8704"
            and effective_gross_mass is not None
            and not inferred_mass_near_category_boundary
        ):
            if effective_gross_mass <= 3500:
                technical_category = VehicleTechnicalCategory.N1
            elif effective_gross_mass <= 12000:
                technical_category = VehicleTechnicalCategory.N2
            else:
                technical_category = VehicleTechnicalCategory.N3
    if technical_category is not None:
        evidence = [
            InferenceEvidence(
                source="vehicle_classification",
                marker="tnved_heading",
                raw_value=technical_classification.tnved_heading,
            )
        ]
        if technical_category != VehicleTechnicalCategory.M1:
            evidence.append(
                _normalized_evidence("gross_mass_kg", effective_gross_mass)
            )
        decisions["vehicle_technical_category"] = InferenceDecision(
            value=technical_category,
            rule_code=f"TECHNICAL_CATEGORY_{technical_category.value}",
            confidence=(
                InferenceConfidence.MEDIUM
                if inferred_gross_mass is not None
                else InferenceConfidence.HIGH
            ),
            evidence=tuple(evidence),
        )
    category_status = technical_classification.status
    category_missing_fields = list(technical_classification.missing_fields)
    category_reason = technical_classification.details.get("reason")
    if (
        technical_classification.status == ClassificationStatus.CLASSIFIED
        and technical_classification.tnved_heading in {"8702", "8704"}
        and effective_gross_mass is None
    ):
        category_status = ClassificationStatus.MISSING_DATA
        category_missing_fields = ["gross_mass_kg"]
        category_reason = "TECHNICAL_CATEGORY_REQUIRES_GROSS_MASS"
    elif inferred_mass_near_category_boundary:
        category_status = ClassificationStatus.MANUAL_REVIEW
        category_missing_fields = []
        category_reason = "INFERRED_GROSS_MASS_NEAR_CATEGORY_BOUNDARY"
    technical_category_details = {
        "status": category_status.value,
        "tnved_heading": technical_classification.tnved_heading,
        "classification_rule_code": technical_classification.rule_code,
        "missing_fields": category_missing_fields,
        "reason": category_reason,
        "classification_details": technical_classification.details,
    }
    flags = (INFERRED_INPUTS_USED,) if decisions else ()
    return VehicleAttributeInferenceResult(
        decisions=decisions,
        warnings=warnings,
        flags=flags,
        details={
            "vehicle_technical_category": technical_category_details,
        },
    )


def _json_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _previously_inferred_fields(row: Mapping[str, Any]) -> set[str]:
    details = row.get("inference_details_json")
    if not isinstance(details, Mapping):
        return set()
    decisions = details.get("decisions")
    if not isinstance(decisions, Mapping):
        return set()
    return {
        str(field_name)
        for field_name, decision in decisions.items()
        if isinstance(decision, Mapping) and decision.get("outcome") == "APPLIED"
    }


def apply_vehicle_attribute_inference(
    row: Mapping[str, Any],
    parameters: Iterable[RawParameter],
    *,
    spec_name: str | None = None,
    series_name: str | None = None,
) -> dict[str, Any]:
    """Применить вывод к строке, не заменяя явно заданные значения."""
    updated = dict(row)
    previous_inferred = _previously_inferred_fields(row)
    inference_input = dict(updated)
    for field_name in previous_inferred:
        inference_input[field_name] = None
    result = infer_vehicle_attributes(
        parameters,
        body_type=inference_input.get("body_type"),
        vehicle_class=inference_input.get("vehicle_class"),
        seat_count_min=inference_input.get("seat_count_min"),
        seat_count_max=inference_input.get("seat_count_max"),
        curb_mass_kg=inference_input.get("curb_mass_kg"),
        gross_mass_kg=inference_input.get("gross_mass_kg"),
        payload_kg_min=inference_input.get("payload_kg_min"),
        payload_kg_max=inference_input.get("payload_kg_max"),
        length_mm=inference_input.get("length_mm"),
        wheelbase_mm=inference_input.get("wheelbase_mm"),
        cargo_length_min_mm=inference_input.get("cargo_length_min_mm"),
        cargo_length_max_mm=inference_input.get("cargo_length_max_mm"),
        cargo_width_min_mm=inference_input.get("cargo_width_min_mm"),
        cargo_width_max_mm=inference_input.get("cargo_width_max_mm"),
        cargo_height_min_mm=inference_input.get("cargo_height_min_mm"),
        cargo_height_max_mm=inference_input.get("cargo_height_max_mm"),
        has_permanent_rear_seats=inference_input.get("has_permanent_rear_seats"),
        has_rear_side_windows=inference_input.get("has_rear_side_windows"),
        has_rear_windowed_door=inference_input.get("has_rear_windowed_door"),
        has_separate_cargo_compartment=inference_input.get(
            "has_separate_cargo_compartment"
        ),
        is_special_purpose=inference_input.get("is_special_purpose"),
        spec_name=spec_name,
        series_name=series_name,
    )

    warnings = [
        warning
        for warning in (updated.get("warnings_json") or [])
        if not (
            isinstance(warning, Mapping)
            and warning.get("code") == "INFERENCE_CONFLICT"
        )
    ]
    serialized_decisions: dict[str, dict[str, Any]] = {}
    applied_fields: set[str] = set()
    for field_name in previous_inferred - result.decisions.keys():
        if field_name in INFERRED_STORAGE_FIELDS:
            updated[field_name] = None
    for field_name, decision in result.decisions.items():
        if field_name not in INFERRED_STORAGE_FIELDS:
            continue
        inferred_value = _json_value(decision.value)
        current_value = updated.get(field_name)
        can_replace = current_value is None or field_name in previous_inferred
        if can_replace:
            updated[field_name] = inferred_value
            outcome = "APPLIED"
            applied_fields.add(field_name)
        elif current_value == inferred_value:
            outcome = "CONFIRMED_EXPLICIT"
        else:
            outcome = "CONFLICT_EXPLICIT"
            warnings.append(
                {
                    "code": "INFERENCE_CONFLICT",
                    "field": field_name,
                    "explicit_value": current_value,
                    "inferred_value": inferred_value,
                    "rule_code": decision.rule_code,
                }
            )
        serialized_decisions[field_name] = {
            "value": inferred_value,
            "outcome": outcome,
            "rule_code": decision.rule_code,
            "confidence": decision.confidence.value,
            "evidence": [
                {
                    "source": evidence.source,
                    "marker": evidence.marker,
                    "raw_value": evidence.raw_value,
                }
                for evidence in decision.evidence
            ],
        }

    updated["warnings_json"] = warnings
    updated["inference_details_json"] = {
        "decisions": serialized_decisions,
        "warnings": list(result.warnings),
        **result.details,
    }
    updated["inference_flags_json"] = (
        [INFERRED_INPUTS_USED] if applied_fields else []
    )
    updated["inference_rules_version"] = result.rules_version
    return updated
