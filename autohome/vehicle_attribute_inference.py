from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any, Iterable, Mapping


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

    value: bool | VehiclePurposeType
    rule_code: str
    confidence: InferenceConfidence
    evidence: tuple[InferenceEvidence, ...]


@dataclass(frozen=True)
class VehicleAttributeInferenceResult:
    """Результат косвенного вывода без изменения исходных данных."""

    decisions: dict[str, InferenceDecision] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def value(self, field_name: str) -> bool | VehiclePurposeType | None:
        decision = self.decisions.get(field_name)
        return decision.value if decision is not None else None


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


def infer_vehicle_attributes(
    parameters: Iterable[RawParameter],
    *,
    body_type: str | None,
    spec_name: str | None = None,
    series_name: str | None = None,
) -> VehicleAttributeInferenceResult:
    """Выполнить все косвенные правила для одной комплектации."""
    decisions = infer_parameter_attributes(parameters, body_type=body_type)
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
    return VehicleAttributeInferenceResult(decisions=decisions, warnings=warnings)
