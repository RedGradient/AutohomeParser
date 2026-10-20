from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import blake2b

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from autohome.import_duty import (
    CLASSIFICATION_RULES_VERSION,
    DutyContext,
    ExchangeRate,
    ImporterType,
    VehicleClassificationInput,
    calculate_import_duty,
    classify_vehicle,
)
from autohome.import_duty.calculator import assumed_production_date, completed_months
from autohome.import_duty.currency import fetch_cbr_rates
from autohome.import_duty.detail_labels import add_detail_field_labels
from autohome.import_duty.rates import RULES_VERSION
from autohome.import_duty.types import (
    CalculationStatus,
    ClassificationStatus,
    DutyResult,
)
from autohome.models import (
    CustomsCalculation,
    CustomsPaymentResult,
    Spec,
    SpecPowertrain,
    SpecVehicleAttributes,
)
from autohome.vehicle_attribute_inference import INFERRED_INPUTS_USED
from autohome.vehicle_attribute_schema import ensure_vehicle_attribute_schema

MAX_UPSERT_ROWS = 2000


def parse_arguments() -> argparse.Namespace:
    """Разобрать параметры массового расчёта."""
    parser = argparse.ArgumentParser(
        description="Рассчитать ввозную пошлину автомобилей Китай → Россия."
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


def make_rows(
    row,
    importer: ImporterType,
    calculation_date: date,
    rates,
    classification=None,
):
    """Рассчитать один сценарий и сериализовать две строки БД."""
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
    calculation_id = stable_calculation_id(
        row.id, importer, calculation_date, price_source
    )
    now = datetime.now(timezone.utc)
    inference_flags = getattr(row, "inference_flags_json", None) or []
    inference_details = getattr(row, "inference_details_json", None) or {}
    calculation_warnings = list(result.warnings)
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
            "guide_price_cny": str(row.guide_price_yuan) if row.guide_price_yuan is not None else None,
            "dealer_price_cny": str(row.dealer_price_yuan) if row.dealer_price_yuan is not None else None,
            "selected_price_cny": str(price_cny) if price_cny is not None else None,
            "price_source": price_source,
            "model_year": row.year,
            "energy_type": row.energy_type,
            "body_type": row.body_type,
            "engine_displacement_cc": row.engine_displacement_ml,
            "engine_power_hp": str(row.engine_power_hp) if row.engine_power_hp is not None else None,
            "motor_power_kw": str(row.motor_total_power_kw) if row.motor_total_power_kw is not None else None,
            "vehicle_class": getattr(row, "vehicle_class", None),
            "axle_count": getattr(row, "axle_count", None),
            "seat_count_min": getattr(row, "seat_count_min", None),
            "seat_count_max": getattr(row, "seat_count_max", None),
            "gross_mass_kg": getattr(row, "gross_mass_kg", None),
            "curb_mass_kg": getattr(row, "curb_mass_kg", None),
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
    payment = {
        "calculation_id": calculation_id,
        "payment_type": "IMPORT_DUTY",
        "amount_rub": result.amount_rub,
        "status": result.status.value,
        "rule_code": result.rule_code,
        "details_json": add_detail_field_labels(result.details),
    }
    return calculation, payment


def dialect_insert(engine, model):
    """Выбрать INSERT с поддержкой UPSERT для PostgreSQL или SQLite."""
    if engine.dialect.name == "postgresql":
        return postgresql_insert(model)
    if engine.dialect.name == "sqlite":
        return sqlite_insert(model)
    raise RuntimeError(f"Неподдерживаемая БД: {engine.dialect.name}")


def upsert_batch(engine, calculations: list[dict], payments: list[dict]) -> None:
    """Атомарно записать пакет сценариев и результатов пошлины."""
    if len(calculations) != len(payments):
        raise ValueError("Число расчётов и результатов платежей не совпадает")
    with engine.begin() as connection:
        for start in range(0, len(calculations), MAX_UPSERT_ROWS):
            calculation_chunk = calculations[start : start + MAX_UPSERT_ROWS]
            payment_chunk = payments[start : start + MAX_UPSERT_ROWS]
            calculation_insert = dialect_insert(engine, CustomsCalculation).values(
                calculation_chunk
            )
            calculation_update = {
                column.name: getattr(calculation_insert.excluded, column.name)
                for column in CustomsCalculation.__table__.columns
                if column.name != "id"
            }
            payment_insert = dialect_insert(engine, CustomsPaymentResult).values(
                payment_chunk
            )
            payment_update = {
                column.name: getattr(payment_insert.excluded, column.name)
                for column in CustomsPaymentResult.__table__.columns
                if column.name not in {"calculation_id", "payment_type"}
            }
            connection.execute(
                calculation_insert.on_conflict_do_update(
                    index_elements=["id"], set_=calculation_update
                )
            )
            connection.execute(
                payment_insert.on_conflict_do_update(
                    index_elements=["calculation_id", "payment_type"],
                    set_=payment_update,
                )
            )


def main() -> int:
    """Выполнить массовый расчёт пошлины."""
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
            Spec.guide_price_yuan,
            Spec.dealer_price_yuan,
            Spec.year,
            SpecPowertrain.energy_type,
            SpecPowertrain.engine_displacement_ml,
            SpecPowertrain.engine_power_hp,
            SpecPowertrain.motor_total_power_kw,
            SpecVehicleAttributes.vehicle_class,
            SpecVehicleAttributes.body_type,
            SpecVehicleAttributes.seat_count_min,
            SpecVehicleAttributes.seat_count_max,
            SpecVehicleAttributes.gross_mass_kg,
            SpecVehicleAttributes.curb_mass_kg,
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
            *inference_select_columns,
        )
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
                    calculation, payment = make_rows(
                        row,
                        importer,
                        args.calculation_date,
                        rates,
                        classification,
                    )
                    calculations.append(calculation)
                    payments.append(payment)
                    counts[f"{importer.value}:{payment['status']}"] += 1
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
    raise SystemExit(main())
