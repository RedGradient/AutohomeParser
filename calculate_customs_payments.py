from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import blake2b

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from autohome.import_duty import (
    CLASSIFICATION_RULES_VERSION,
    DutyContext,
    ExchangeRate,
    ExciseContext,
    ImporterType,
    RecyclingFeeContext,
    RecyclingFeeRegulatoryInput,
    RecyclingFeeRegulatorySection,
    RecyclingFeeRoutingStatus,
    RecyclingFeeVehicleKind,
    SectionIIIRecyclingFeeContext,
    SectionIIRecyclingFeeContext,
    SectionIVRecyclingFeeContext,
    SectionVRecyclingFeeContext,
    VatContext,
    VehicleClassificationInput,
    calculate_customs_fee,
    calculate_excise,
    calculate_import_duty,
    calculate_recycling_fee,
    calculate_section_ii_recycling_fee,
    calculate_section_iii_recycling_fee,
    calculate_section_iv_recycling_fee,
    calculate_section_v_recycling_fee,
    calculate_vat,
    classify_vehicle,
    route_recycling_fee_regulation,
)
from autohome.import_duty.calculator import assumed_production_date, completed_months
from autohome.import_duty.currency import fetch_cbr_rates
from autohome.import_duty.excise import ExciseResult
from autohome.import_duty.excise_rates import EXCISE_RULES_SOURCE, EXCISE_RULES_VERSION
from autohome.import_duty.rates import RULES_VERSION
from autohome.import_duty.recycling_fee import RecyclingFeeResult
from autohome.import_duty.types import (
    CalculationStatus,
    ClassificationStatus,
    DutyResult,
)
from autohome.import_duty.vat import VatResult
from autohome.import_duty.vat_rates import (
    VAT_BASE_RULES_SOURCE,
    VAT_RATE_RULES_SOURCE,
    VAT_RULES_VERSION,
)
from autohome.models import (
    CustomsCalculation,
    CustomsPaymentResult,
    Series,
    Spec,
    SpecPowertrain,
    SpecVehicleAttributes,
)
from autohome.powertrain_schema import ensure_powertrain_schema
from autohome.vehicle_attribute_inference import INFERRED_INPUTS_USED
from autohome.vehicle_attribute_schema import ensure_vehicle_attribute_schema

MAX_UPSERT_ROWS = 2000
CHASSIS_NAME_RE = re.compile(r"(?:底盘|\bшасси\b)", re.IGNORECASE)


def parse_arguments() -> argparse.Namespace:
    """Разобрать параметры массового расчёта."""
    parser = argparse.ArgumentParser(
        description="Рассчитать таможенные платежи для автомобилей Китай → Россия."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        dest="calculation_date",
        help="Дата расчёта YYYY-MM-DD; по умолчанию сегодня.",
    )
    parser.add_argument(
        "--importers",
        default="individual,legal_entity",
        help="individual, legal_entity или оба через запятую.",
    )
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--individual-personal-use",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Считать сценарий физлица ввозом для личного пользования; "
            "по умолчанию включено."
        ),
    )
    parser.add_argument("--cny-rate-rub", type=Decimal)
    parser.add_argument("--cny-nominal", type=int, default=10)
    parser.add_argument("--eur-rate-rub", type=Decimal)
    parser.add_argument("--eur-nominal", type=int, default=1)
    return parser.parse_args()


def parse_importers(value: str) -> list[ImporterType]:
    """Преобразовать CLI-список импортёров в enum."""
    aliases = {
        "individual": ImporterType.INDIVIDUAL,
        "legal_entity": ImporterType.LEGAL_ENTITY,
    }
    result = []
    for item in value.split(","):
        key = item.strip().lower()
        if key not in aliases:
            raise SystemExit(f"Неизвестный тип импортёра: {item!r}")
        if aliases[key] not in result:
            result.append(aliases[key])
    return result


def resolve_rates(args: argparse.Namespace) -> dict[str, ExchangeRate]:
    """Получить курсы ЦБ либо принять явно заданные значения."""
    supplied = args.cny_rate_rub is not None or args.eur_rate_rub is not None
    if supplied:
        if args.cny_rate_rub is None or args.eur_rate_rub is None:
            raise SystemExit("Задайте одновременно --cny-rate-rub и --eur-rate-rub")
        return {
            "CNY": ExchangeRate(
                "CNY", args.cny_nominal, args.cny_rate_rub, args.calculation_date
            ),
            "EUR": ExchangeRate(
                "EUR", args.eur_nominal, args.eur_rate_rub, args.calculation_date
            ),
        }
    return fetch_cbr_rates(args.calculation_date)


def stable_calculation_id(
    spec_id: int,
    importer_type: ImporterType,
    calculation_date: date,
    price_source: str,
) -> int:
    """Получить воспроизводимый положительный BIGINT для сценария."""
    value = "|".join(
        (
            str(spec_id),
            importer_type.value,
            calculation_date.isoformat(),
            RULES_VERSION,
            price_source,
        )
    )
    return int.from_bytes(blake2b(value.encode(), digest_size=8).digest(), "big") >> 1


def select_vehicle_price(
    guide_price_yuan: Decimal | None,
    dealer_price_yuan: Decimal | None,
) -> tuple[Decimal | None, str]:
    """Выбрать положительную цену с приоритетом каталожной."""
    if guide_price_yuan is not None and guide_price_yuan > 0:
        return guide_price_yuan, "GUIDE"
    if dealer_price_yuan is not None and dealer_price_yuan > 0:
        return dealer_price_yuan, "DEALER"
    return None, "MISSING"


def classify_database_row(row):
    """Классифицировать выбранную SQL-строку общим классификатором."""
    values = VehicleClassificationInput(
        **{
            field: getattr(row, field, None)
            for field in VehicleClassificationInput.__dataclass_fields__
        }
    )
    return classify_vehicle(values)


def classification_failure(result) -> DutyResult:
    """Преобразовать безопасный отказ классификатора в результат расчёта."""
    status_by_classification = {
        ClassificationStatus.AMBIGUOUS: CalculationStatus.MANUAL_REVIEW,
        ClassificationStatus.MISSING_DATA: CalculationStatus.MISSING_DATA,
        ClassificationStatus.MANUAL_REVIEW: CalculationStatus.MANUAL_REVIEW,
        ClassificationStatus.UNSUPPORTED: CalculationStatus.UNSUPPORTED,
    }
    calculation_status = status_by_classification.get(
        result.status,
        CalculationStatus.MANUAL_REVIEW,
    )
    return DutyResult(
        status=calculation_status,
        classification_status=result.status,
        tnved_code=result.tnved_heading,
        details={
            "classification_rules_version": result.rules_version,
            "classification_rule_code": result.rule_code,
            "classification_missing_fields": list(result.missing_fields),
            **result.details,
        },
    )


def recycling_fee_vehicle_kind(row) -> tuple[RecyclingFeeVehicleKind, str]:
    """Определить готовое ТС или шасси по доступным данным каталога."""
    explicit = getattr(row, "recycling_fee_vehicle_kind", None)
    if explicit is not None:
        try:
            return RecyclingFeeVehicleKind(explicit), "NORMALIZED_FIELD"
        except ValueError:
            pass
    names = " ".join(
        str(value)
        for value in (
            getattr(row, "spec_name", None),
            getattr(row, "series_name", None),
        )
        if value
    )
    if CHASSIS_NAME_RE.search(names):
        return RecyclingFeeVehicleKind.CHASSIS, "NAME_MARKER"
    return RecyclingFeeVehicleKind.COMPLETE_VEHICLE, "NO_CHASSIS_NAME_MARKER"


def recycling_routing_failure(route) -> RecyclingFeeResult:
    """Преобразовать отказ нормативной маршрутизации в результат платежа."""
    status_by_route = {
        RecyclingFeeRoutingStatus.MISSING_DATA: CalculationStatus.MISSING_DATA,
        RecyclingFeeRoutingStatus.MANUAL_REVIEW: CalculationStatus.MANUAL_REVIEW,
        RecyclingFeeRoutingStatus.UNSUPPORTED: CalculationStatus.UNSUPPORTED,
    }
    return RecyclingFeeResult(
        status=status_by_route.get(route.status, CalculationStatus.MANUAL_REVIEW),
        rule_code=route.rule_code,
        details={"regulation_route": dict(route.details)},
    )


def calculate_row_recycling_fee(
    row,
    importer: ImporterType,
    calculation_date: date,
    age_months: int | None,
    personal_use: bool,
) -> tuple[RecyclingFeeResult, RecyclingFeeVehicleKind | None, str | None]:
    """Выбрать нормативный раздел и рассчитать утильсбор одной комплектации."""
    category = getattr(row, "vehicle_technical_category", None)
    if category == "M1":
        return (
            calculate_recycling_fee(
                RecyclingFeeContext(
                    importer_type=importer,
                    calculation_date=calculation_date,
                    personal_use=personal_use,
                    vehicle_technical_category=category,
                    age_months=age_months,
                    powertrain_type=getattr(row, "recycling_fee_powertrain_type", None),
                    power_kw=getattr(row, "recycling_fee_power_kw", None),
                    power_source=getattr(row, "recycling_fee_power_source", None),
                    engine_displacement_cc=row.engine_displacement_ml,
                    engine_summary=getattr(row, "engine_summary", None),
                )
            ),
            None,
            None,
        )

    vehicle_kind, vehicle_kind_source = recycling_fee_vehicle_kind(row)
    route = route_recycling_fee_regulation(
        RecyclingFeeRegulatoryInput(
            vehicle_technical_category=category,
            vehicle_kind=vehicle_kind,
            is_special_purpose=getattr(row, "is_special_purpose", None),
            vehicle_purpose_type=getattr(row, "vehicle_purpose_type", None),
        )
    )
    if route.status != RecyclingFeeRoutingStatus.ROUTED:
        return recycling_routing_failure(route), vehicle_kind, vehicle_kind_source

    if route.section == RecyclingFeeRegulatorySection.SECTION_II_N:
        result = calculate_section_ii_recycling_fee(
            SectionIIRecyclingFeeContext(
                calculation_date=calculation_date,
                vehicle_technical_category=category,
                age_months=age_months,
                gross_mass_kg=getattr(row, "gross_mass_kg", None),
            )
        )
    elif route.section == RecyclingFeeRegulatorySection.SECTION_III_SPECIAL:
        result = calculate_section_iii_recycling_fee(
            SectionIIIRecyclingFeeContext(
                calculation_date=calculation_date,
                vehicle_technical_category=category,
                age_months=age_months,
                gross_mass_kg=getattr(row, "gross_mass_kg", None),
                is_special_purpose=getattr(row, "is_special_purpose", None),
                vehicle_purpose_type=getattr(row, "vehicle_purpose_type", None),
            )
        )
    elif route.section == RecyclingFeeRegulatorySection.SECTION_IV_M:
        result = calculate_section_iv_recycling_fee(
            SectionIVRecyclingFeeContext(
                calculation_date=calculation_date,
                vehicle_technical_category=category,
                age_months=age_months,
                powertrain_type=getattr(row, "recycling_fee_powertrain_type", None),
                engine_displacement_cc=row.engine_displacement_ml,
            )
        )
    elif route.section == RecyclingFeeRegulatorySection.SECTION_V_CHASSIS:
        result = calculate_section_v_recycling_fee(
            SectionVRecyclingFeeContext(
                calculation_date=calculation_date,
                vehicle_technical_category=category,
                vehicle_kind=vehicle_kind,
                age_months=age_months,
                gross_mass_kg=getattr(row, "gross_mass_kg", None),
            )
        )
    else:
        return recycling_routing_failure(route), vehicle_kind, vehicle_kind_source

    result.details["regulation_route"] = dict(route.details)
    result.details["recycling_fee_vehicle_kind"] = vehicle_kind.value
    result.details["recycling_fee_vehicle_kind_source"] = vehicle_kind_source
    return result, vehicle_kind, vehicle_kind_source


def calculate_row_excise(
    row,
    importer: ImporterType,
    calculation_date: date,
) -> ExciseResult:
    """Определить применимость и рассчитать акциз одного автомобиля."""
    common_details = {
        "source": EXCISE_RULES_SOURCE,
        "rules_version": EXCISE_RULES_VERSION,
    }
    if importer == ImporterType.INDIVIDUAL:
        return ExciseResult(
            status=CalculationStatus.NOT_APPLICABLE,
            rule_code="EXCISE_NOT_APPLICABLE_PERSONAL_USE",
            details={**common_details, "reason": "PERSONAL_USE"},
        )

    category = getattr(row, "vehicle_technical_category", None)
    if category in {"M2", "M3", "N1", "N2", "N3"}:
        return ExciseResult(
            status=CalculationStatus.NOT_APPLICABLE,
            rule_code="EXCISE_NOT_APPLICABLE_VEHICLE_CATEGORY",
            details={
                **common_details,
                "reason": "VEHICLE_CATEGORY",
                "vehicle_technical_category": category,
            },
        )
    if category != "M1":
        return ExciseResult(
            status=CalculationStatus.MANUAL_REVIEW,
            rule_code="EXCISE_VEHICLE_CATEGORY_REQUIRES_REVIEW",
            details={
                **common_details,
                "reason": "UNKNOWN_VEHICLE_CATEGORY",
                "vehicle_technical_category": category,
            },
        )
    return calculate_excise(
        ExciseContext(
            calculation_date=calculation_date,
            energy_type=row.energy_type,
            engine_power_kw=getattr(row, "engine_power_kw", None),
            engine_power_hp=row.engine_power_hp,
            normative_power_kw=getattr(row, "recycling_fee_power_kw", None),
            normative_power_source=getattr(
                row,
                "recycling_fee_power_source",
                None,
            ),
        )
    )


def calculate_row_vat(
    importer: ImporterType,
    calculation_date: date,
    customs_value_rub: Decimal | None,
    import_duty_result: DutyResult,
    excise_result: ExciseResult,
) -> VatResult:
    """Определить применимость и рассчитать НДС одного автомобиля."""
    common_details = {
        "rate_source": VAT_RATE_RULES_SOURCE,
        "tax_base_source": VAT_BASE_RULES_SOURCE,
        "rules_version": VAT_RULES_VERSION,
    }
    if importer == ImporterType.INDIVIDUAL:
        return VatResult(
            status=CalculationStatus.NOT_APPLICABLE,
            rule_code="VAT_NOT_APPLICABLE_PERSONAL_USE",
            details={**common_details, "reason": "PERSONAL_USE"},
        )

    if import_duty_result.status != CalculationStatus.CALCULATED:
        return VatResult(
            status=import_duty_result.status,
            rule_code="VAT_BLOCKED_BY_IMPORT_DUTY",
            details={
                **common_details,
                "reason": "IMPORT_DUTY_NOT_CALCULATED",
                "dependency_status": import_duty_result.status.value,
            },
        )

    if excise_result.status != CalculationStatus.CALCULATED:
        status = excise_result.status
        if status == CalculationStatus.NOT_APPLICABLE:
            status = CalculationStatus.UNSUPPORTED
        return VatResult(
            status=status,
            rule_code="VAT_BLOCKED_BY_EXCISE",
            details={
                **common_details,
                "reason": "EXCISE_NOT_CALCULATED",
                "dependency_status": excise_result.status.value,
            },
        )

    return calculate_vat(
        VatContext(
            calculation_date=calculation_date,
            customs_value_rub=customs_value_rub,
            import_duty_rub=import_duty_result.amount_rub,
            excise_rub=excise_result.amount_rub,
        )
    )


def make_rows(
    row,
    importer: ImporterType,
    calculation_date: date,
    rates,
    classification=None,
    personal_use: bool | None = None,
):
    """Рассчитать один сценарий и сериализовать его строки платежей."""
    if classification is None:
        classification = classify_database_row(row)
    price_cny, price_source = select_vehicle_price(
        row.guide_price_yuan, row.dealer_price_yuan
    )
    context = DutyContext(
        spec_id=row.id,
        importer_type=importer,
        calculation_date=calculation_date,
        price_cny=price_cny,
        cny_rate=rates["CNY"],
        eur_rate=rates["EUR"],
        model_year=row.year,
        energy_type=row.energy_type,
        body_type=row.body_type,
        engine_displacement_cc=row.engine_displacement_ml,
        engine_power_hp=row.engine_power_hp,
        motor_power_kw=row.motor_total_power_kw,
        price_source=price_source,
        tnved_heading=classification.tnved_heading,
        gross_mass_kg=getattr(row, "gross_mass_kg", None),
        seat_count_max=getattr(row, "seat_count_max", None),
        is_special_purpose=getattr(row, "is_special_purpose", None),
    )
    if classification.status == ClassificationStatus.CLASSIFIED:
        result = calculate_import_duty(context)
    else:
        result = classification_failure(classification)
    if price_cny is None and result.status.value == "CALCULATED":
        price_source = "NOT_REQUIRED"
    production_date = assumed_production_date(row.year)
    age_months = (
        completed_months(production_date, calculation_date)
        if production_date is not None
        else None
    )
    customs_value_rub = None
    if price_cny is not None:
        customs_value_rub = (price_cny * rates["CNY"].rub_per_unit).quantize(
            Decimal("0.01")
        )
    customs_fee_result = calculate_customs_fee(customs_value_rub, calculation_date)
    if personal_use is None:
        personal_use = importer == ImporterType.INDIVIDUAL
    recycling_fee_result, recycling_vehicle_kind, recycling_vehicle_kind_source = (
        calculate_row_recycling_fee(
            row,
            importer,
            calculation_date,
            age_months,
            personal_use,
        )
    )
    excise_result = calculate_row_excise(row, importer, calculation_date)
    vat_result = calculate_row_vat(
        importer,
        calculation_date,
        customs_value_rub,
        result,
        excise_result,
    )
    calculation_id = stable_calculation_id(
        row.id, importer, calculation_date, price_source
    )
    now = datetime.now(UTC)
    inference_flags = getattr(row, "inference_flags_json", None) or []
    inference_details = getattr(row, "inference_details_json", None) or {}
    calculation_warnings = list(result.warnings)
    if customs_fee_result.status == CalculationStatus.CALCULATED:
        calculation_warnings.append(
            {
                "code": "INCOMPLETE_CUSTOMS_VALUE",
                "message": (
                    "Таможенная стоимость рассчитана только по цене автомобиля "
                    "и не включает доставку, страхование и другие расходы."
                ),
                "fields": ["customs_value_rub"],
            }
        )
    if INFERRED_INPUTS_USED in inference_flags:
        applied_fields = sorted(
            field_name
            for field_name, decision in (
                inference_details.get("decisions") or {}
            ).items()
            if decision.get("outcome") == "APPLIED"
        )
        calculation_warnings.append(
            {
                "code": INFERRED_INPUTS_USED,
                "message": "В расчёте использованы косвенно определённые признаки.",
                "fields": applied_fields,
            }
        )
    if recycling_vehicle_kind_source in {
        "NAME_MARKER",
        "NO_CHASSIS_NAME_MARKER",
    }:
        calculation_warnings.append(
            {
                "code": INFERRED_INPUTS_USED,
                "message": (
                    "Вид объекта утильсбора определён по наличию маркера шасси "
                    "в названии комплектации или серии."
                ),
                "fields": ["recycling_fee_vehicle_kind"],
            }
        )
    if (
        recycling_fee_result.details.get("engine_volume_source")
        == "ENGINE_SUMMARY_NOMINAL_VOLUME"
    ):
        calculation_warnings.append(
            {
                "code": INFERRED_INPUTS_USED,
                "message": (
                    "Диапазон объёма двигателя для утильсбора определён "
                    "по обозначению двигателя."
                ),
                "fields": ["recycling_fee_engine_volume_band"],
            }
        )
    calculation = {
        "id": calculation_id,
        "spec_id": row.id,
        "importer_type": importer.value,
        "calculation_date": calculation_date,
        "rules_version": RULES_VERSION,
        "price_source": price_source,
        "vehicle_price_cny": price_cny,
        "customs_value_rub": customs_value_rub,
        "cny_rate_nominal": rates["CNY"].nominal,
        "cny_rate_rub": rates["CNY"].rate_rub,
        "cny_rate_date": rates["CNY"].rate_date,
        "eur_rate_nominal": rates["EUR"].nominal,
        "eur_rate_rub": rates["EUR"].rate_rub,
        "eur_rate_date": rates["EUR"].rate_date,
        "model_year": row.year,
        "assumed_production_date": production_date,
        "age_months": age_months,
        "energy_type": row.energy_type,
        "body_type": row.body_type,
        "engine_displacement_ml": row.engine_displacement_ml,
        "tnved_code": result.tnved_code,
        "classification_status": result.classification_status.value,
        "status": result.status.value,
        "input_snapshot_json": {
            "spec_id": row.id,
            "guide_price_cny": str(row.guide_price_yuan)
            if row.guide_price_yuan is not None
            else None,
            "dealer_price_cny": str(row.dealer_price_yuan)
            if row.dealer_price_yuan is not None
            else None,
            "selected_price_cny": str(price_cny) if price_cny is not None else None,
            "price_source": price_source,
            "model_year": row.year,
            "energy_type": row.energy_type,
            "body_type": row.body_type,
            "engine_displacement_cc": row.engine_displacement_ml,
            "engine_summary": getattr(row, "engine_summary", None),
            "engine_power_kw": str(row.engine_power_kw)
            if getattr(row, "engine_power_kw", None) is not None
            else None,
            "engine_power_hp": str(row.engine_power_hp)
            if row.engine_power_hp is not None
            else None,
            "motor_power_kw": str(row.motor_total_power_kw)
            if row.motor_total_power_kw is not None
            else None,
            "personal_use": personal_use,
            "vehicle_technical_category": getattr(
                row, "vehicle_technical_category", None
            ),
            "recycling_fee_powertrain_type": getattr(
                row, "recycling_fee_powertrain_type", None
            ),
            "recycling_fee_power_kw": (
                str(row.recycling_fee_power_kw)
                if getattr(row, "recycling_fee_power_kw", None) is not None
                else None
            ),
            "recycling_fee_power_source": getattr(
                row, "recycling_fee_power_source", None
            ),
            "recycling_fee_vehicle_kind": (
                recycling_vehicle_kind.value if recycling_vehicle_kind else None
            ),
            "recycling_fee_vehicle_kind_source": recycling_vehicle_kind_source,
            "vehicle_class": getattr(row, "vehicle_class", None),
            "axle_count": getattr(row, "axle_count", None),
            "seat_count_min": getattr(row, "seat_count_min", None),
            "seat_count_max": getattr(row, "seat_count_max", None),
            "gross_mass_kg": getattr(row, "gross_mass_kg", None),
            "curb_mass_kg": getattr(row, "curb_mass_kg", None),
            "curb_mass_kg_min": getattr(row, "curb_mass_kg_min", None),
            "curb_mass_kg_max": getattr(row, "curb_mass_kg_max", None),
            "payload_kg_min": getattr(row, "payload_kg_min", None),
            "payload_kg_max": getattr(row, "payload_kg_max", None),
            "wheelbase_mm": getattr(row, "wheelbase_mm", None),
            "cargo_length_min_mm": getattr(
                row,
                "cargo_length_min_mm",
                None,
            ),
            "cargo_length_max_mm": getattr(
                row,
                "cargo_length_max_mm",
                None,
            ),
            "is_special_purpose": getattr(row, "is_special_purpose", None),
            "vehicle_purpose_type": getattr(row, "vehicle_purpose_type", None),
            "classification_rules_version": CLASSIFICATION_RULES_VERSION,
            "classification_status": classification.status.value,
            "classification_tnved_heading": classification.tnved_heading,
            "classification_rule_code": classification.rule_code,
            "classification_missing_fields": list(classification.missing_fields),
            "classification_details": classification.details,
            "vehicle_attribute_inference_flags": inference_flags,
            "vehicle_attribute_inference_rules_version": getattr(
                row,
                "inference_rules_version",
                None,
            ),
            "vehicle_attribute_inference_details": inference_details,
        },
        "warnings_json": calculation_warnings,
        "calculated_at": now,
    }
    payments = [
        {
            "calculation_id": calculation_id,
            "payment_type": "IMPORT_DUTY",
            "amount_rub": result.amount_rub,
            "status": result.status.value,
            "rule_code": result.rule_code,
            "details_json": dict(result.details),
        },
        {
            "calculation_id": calculation_id,
            "payment_type": "CUSTOMS_FEE",
            "amount_rub": customs_fee_result.amount_rub,
            "status": customs_fee_result.status.value,
            "rule_code": customs_fee_result.rule_code,
            "details_json": dict(customs_fee_result.details),
        },
        {
            "calculation_id": calculation_id,
            "payment_type": "RECYCLING_FEE",
            "amount_rub": recycling_fee_result.amount_rub,
            "status": recycling_fee_result.status.value,
            "rule_code": recycling_fee_result.rule_code,
            "details_json": dict(recycling_fee_result.details),
        },
    ]
    payments.append(
        {
            "calculation_id": calculation_id,
            "payment_type": "EXCISE",
            "amount_rub": excise_result.amount_rub,
            "status": excise_result.status.value,
            "rule_code": excise_result.rule_code,
            "details_json": dict(excise_result.details),
        }
    )
    payments.append(
        {
            "calculation_id": calculation_id,
            "payment_type": "VAT",
            "amount_rub": vat_result.amount_rub,
            "status": vat_result.status.value,
            "rule_code": vat_result.rule_code,
            "details_json": dict(vat_result.details),
        }
    )
    return calculation, payments


def dialect_insert(engine, model):
    """Выбрать INSERT с поддержкой UPSERT для PostgreSQL или SQLite."""
    if engine.dialect.name == "postgresql":
        return postgresql_insert(model)
    if engine.dialect.name == "sqlite":
        return sqlite_insert(model)
    raise RuntimeError(f"Неподдерживаемая БД: {engine.dialect.name}")


def upsert_batch(engine, calculations: list[dict], payments: list[dict]) -> None:
    """Атомарно записать пакет сценариев и связанных платежей."""
    with engine.begin() as connection:
        for start in range(0, len(calculations), MAX_UPSERT_ROWS):
            calculation_chunk = calculations[start : start + MAX_UPSERT_ROWS]
            calculation_insert = dialect_insert(engine, CustomsCalculation).values(
                calculation_chunk
            )
            calculation_update = {
                column.name: getattr(calculation_insert.excluded, column.name)
                for column in CustomsCalculation.__table__.columns
                if column.name != "id"
            }
            connection.execute(
                calculation_insert.on_conflict_do_update(
                    index_elements=["id"], set_=calculation_update
                )
            )
        for start in range(0, len(payments), MAX_UPSERT_ROWS):
            payment_chunk = payments[start : start + MAX_UPSERT_ROWS]
            payment_insert = dialect_insert(engine, CustomsPaymentResult).values(
                payment_chunk
            )
            payment_update = {
                column.name: getattr(payment_insert.excluded, column.name)
                for column in CustomsPaymentResult.__table__.columns
                if column.name not in {"calculation_id", "payment_type"}
            }
            connection.execute(
                payment_insert.on_conflict_do_update(
                    index_elements=["calculation_id", "payment_type"],
                    set_=payment_update,
                )
            )


def calculate_customs_payments() -> int:
    """Выполнить массовый расчёт всех поддерживаемых таможенных платежей."""
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size должен быть положительным")
    importers = parse_importers(args.importers)
    rates = resolve_rates(args)
    engine = create_engine(args.database_url, pool_pre_ping=True)
    if not args.dry_run:
        ensure_vehicle_attribute_schema(engine)
        ensure_powertrain_schema(engine)

    existing_vehicle_attribute_columns = {
        column["name"]
        for column in inspect(engine).get_columns("spec_vehicle_attributes")
    }
    inference_select_columns = [
        getattr(SpecVehicleAttributes, name)
        for name in (
            "inference_details_json",
            "inference_flags_json",
            "inference_rules_version",
        )
        if name in existing_vehicle_attribute_columns
    ]

    query = (
        select(
            Spec.id,
            Spec.name.label("spec_name"),
            Series.name.label("series_name"),
            Spec.guide_price_yuan,
            Spec.dealer_price_yuan,
            Spec.year,
            SpecPowertrain.energy_type,
            SpecPowertrain.engine_displacement_ml,
            SpecPowertrain.engine_summary,
            SpecPowertrain.engine_power_kw,
            SpecPowertrain.engine_power_hp,
            SpecPowertrain.motor_total_power_kw,
            SpecPowertrain.recycling_fee_powertrain_type,
            SpecPowertrain.recycling_fee_power_kw,
            SpecPowertrain.recycling_fee_power_source,
            SpecVehicleAttributes.vehicle_class,
            SpecVehicleAttributes.vehicle_technical_category,
            SpecVehicleAttributes.body_type,
            SpecVehicleAttributes.seat_count_min,
            SpecVehicleAttributes.seat_count_max,
            SpecVehicleAttributes.gross_mass_kg,
            SpecVehicleAttributes.curb_mass_kg,
            *(
                getattr(SpecVehicleAttributes, name)
                for name in ("curb_mass_kg_min", "curb_mass_kg_max")
                if name in existing_vehicle_attribute_columns
            ),
            SpecVehicleAttributes.payload_kg_min,
            SpecVehicleAttributes.payload_kg_max,
            SpecVehicleAttributes.length_mm,
            SpecVehicleAttributes.wheelbase_mm,
            SpecVehicleAttributes.cargo_length_min_mm,
            SpecVehicleAttributes.cargo_length_max_mm,
            SpecVehicleAttributes.cargo_width_min_mm,
            SpecVehicleAttributes.cargo_width_max_mm,
            SpecVehicleAttributes.cargo_height_min_mm,
            SpecVehicleAttributes.cargo_height_max_mm,
            SpecVehicleAttributes.has_permanent_rear_seats,
            SpecVehicleAttributes.has_rear_side_windows,
            SpecVehicleAttributes.has_rear_windowed_door,
            SpecVehicleAttributes.has_separate_cargo_compartment,
            SpecVehicleAttributes.is_special_purpose,
            SpecVehicleAttributes.vehicle_purpose_type,
            *inference_select_columns,
        )
        .join(Series, Series.id == Spec.series_id)
        .outerjoin(SpecPowertrain, SpecPowertrain.spec_id == Spec.id)
        .outerjoin(
            SpecVehicleAttributes,
            SpecVehicleAttributes.spec_id == Spec.id,
        )
        .order_by(Spec.id)
    )
    if args.limit:
        query = query.limit(args.limit)

    counts: Counter[str] = Counter()
    calculations: list[dict] = []
    payments: list[dict] = []
    processed_specs = 0
    try:
        with engine.connect() as connection:
            rows = connection.execution_options(stream_results=True).execute(query)
            for row in rows:
                processed_specs += 1
                classification = classify_database_row(row)
                counts[f"CLASSIFICATION:{classification.status.value}"] += 1
                if classification.tnved_heading:
                    counts[f"HEADING:{classification.tnved_heading}"] += 1
                for importer in importers:
                    calculation, scenario_payments = make_rows(
                        row,
                        importer,
                        args.calculation_date,
                        rates,
                        classification,
                        personal_use=(
                            args.individual_personal_use
                            if importer == ImporterType.INDIVIDUAL
                            else False
                        ),
                    )
                    calculations.append(calculation)
                    payments.extend(scenario_payments)
                    for payment in scenario_payments:
                        counts[
                            f"{importer.value}:{payment['payment_type']}:{payment['status']}"
                        ] += 1
                if len(calculations) >= args.batch_size:
                    if not args.dry_run:
                        upsert_batch(engine, calculations, payments)
                    calculations.clear()
                    payments.clear()
                    print(f"Обработано комплектаций: {processed_specs}", flush=True)
        if calculations and not args.dry_run:
            upsert_batch(engine, calculations, payments)
    finally:
        engine.dispose()

    print(f"Дата расчёта: {args.calculation_date}")
    print(
        "Курс CNY: "
        f"{rates['CNY'].rate_rub} RUB за {rates['CNY'].nominal} "
        f"({rates['CNY'].rate_date})"
    )
    print(
        "Курс EUR: "
        f"{rates['EUR'].rate_rub} RUB за {rates['EUR'].nominal} "
        f"({rates['EUR'].rate_date})"
    )
    print(f"Обработано комплектаций: {processed_specs}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    if args.dry_run:
        print("Dry-run: база не изменялась")
    return 0


if __name__ == "__main__":
    raise SystemExit(calculate_customs_payments())
