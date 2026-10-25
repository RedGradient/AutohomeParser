from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

RECYCLING_FEE_REGULATION_SOURCE = (
    "https://www.consultant.ru/document/cons_doc_LAW_156832/"
    "fa680b07af423adb3a41d702b10b38386564470d/"
)


class RecyclingFeeVehicleKind(StrEnum):
    """Вид объекта для выбора раздела нормативной таблицы."""

    COMPLETE_VEHICLE = "COMPLETE_VEHICLE"
    CHASSIS = "CHASSIS"


class RecyclingFeeRegulatorySection(StrEnum):
    """Раздел перечня коэффициентов к ПП РФ № 1291."""

    SECTION_I_M1 = "SECTION_I_M1"
    SECTION_II_N = "SECTION_II_N"
    SECTION_III_SPECIAL = "SECTION_III_SPECIAL"
    SECTION_IV_M = "SECTION_IV_M"
    SECTION_IV_M_REGULAR_ROUTE = "SECTION_IV_M_REGULAR_ROUTE"
    SECTION_V_CHASSIS = "SECTION_V_CHASSIS"


class RecyclingFeeRoutingStatus(StrEnum):
    ROUTED = "ROUTED"
    MISSING_DATA = "MISSING_DATA"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class RecyclingFeeRegulatoryInput:
    vehicle_technical_category: str | None
    vehicle_kind: RecyclingFeeVehicleKind | None = None
    is_special_purpose: bool | None = None
    vehicle_purpose_type: str | None = None
    regular_route_use: bool = False
    regular_route_confirmation: bool | None = None


@dataclass(frozen=True)
class RecyclingFeeRegulatoryResult:
    status: RecyclingFeeRoutingStatus
    section: RecyclingFeeRegulatorySection | None = None
    rule_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _result(
    input_data: RecyclingFeeRegulatoryInput,
    status: RecyclingFeeRoutingStatus,
    *,
    section: RecyclingFeeRegulatorySection | None = None,
    reason: str | None = None,
    missing_fields: tuple[str, ...] = (),
) -> RecyclingFeeRegulatoryResult:
    details: dict[str, Any] = {
        "source": RECYCLING_FEE_REGULATION_SOURCE,
        "vehicle_technical_category": input_data.vehicle_technical_category,
        "vehicle_kind": input_data.vehicle_kind,
        "is_special_purpose": input_data.is_special_purpose,
        "vehicle_purpose_type": input_data.vehicle_purpose_type,
        "regular_route_use": input_data.regular_route_use,
        "regular_route_confirmation": input_data.regular_route_confirmation,
    }
    if reason:
        details["reason"] = reason
    if missing_fields:
        details["missing_fields"] = list(missing_fields)
    return RecyclingFeeRegulatoryResult(
        status=status,
        section=section,
        rule_code=f"RECYCLING_FEE_ROUTE_{section.value}" if section else None,
        details=details,
    )


def route_recycling_fee_regulation(
    input_data: RecyclingFeeRegulatoryInput,
) -> RecyclingFeeRegulatoryResult:
    """Выбрать нормативный раздел, не выбирая конкретный коэффициент."""
    category = input_data.vehicle_technical_category
    if category is None:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.MISSING_DATA,
            missing_fields=("vehicle_technical_category",),
        )
    if category == "M1":
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.ROUTED,
            section=RecyclingFeeRegulatorySection.SECTION_I_M1,
        )
    if category not in {"M2", "M3", "N1", "N2", "N3"}:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.UNSUPPORTED,
            reason="UNSUPPORTED_TECHNICAL_CATEGORY",
        )
    if input_data.vehicle_kind is None:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.MISSING_DATA,
            missing_fields=("recycling_fee_vehicle_kind",),
        )
    if input_data.vehicle_kind == RecyclingFeeVehicleKind.CHASSIS:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.ROUTED,
            section=RecyclingFeeRegulatorySection.SECTION_V_CHASSIS,
        )
    if input_data.is_special_purpose is None:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.MISSING_DATA,
            missing_fields=("is_special_purpose",),
        )
    if input_data.is_special_purpose:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.ROUTED,
            section=RecyclingFeeRegulatorySection.SECTION_III_SPECIAL,
        )
    if category in {"N1", "N2", "N3"}:
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.ROUTED,
            section=RecyclingFeeRegulatorySection.SECTION_II_N,
        )
    if input_data.regular_route_use:
        if input_data.regular_route_confirmation is not True:
            return _result(
                input_data,
                RecyclingFeeRoutingStatus.MANUAL_REVIEW,
                reason="REGULAR_ROUTE_CONFIRMATION_REQUIRED",
            )
        return _result(
            input_data,
            RecyclingFeeRoutingStatus.ROUTED,
            section=RecyclingFeeRegulatorySection.SECTION_IV_M_REGULAR_ROUTE,
        )
    return _result(
        input_data,
        RecyclingFeeRoutingStatus.ROUTED,
        section=RecyclingFeeRegulatorySection.SECTION_IV_M,
    )
