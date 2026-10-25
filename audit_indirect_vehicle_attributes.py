from __future__ import annotations

import argparse
import os
from collections import Counter
from itertools import groupby
from typing import Any

from sqlalchemy import create_engine, select

from autohome.models import (
    ParameterDefinition,
    Series,
    Spec,
    SpecParameter,
    SpecVehicleAttributes,
)
from autohome.vehicle_attribute_inference import (
    PARAMETER_INFERENCE_RULES,
    RawParameter,
    VehicleAttributeInferenceResult,
    infer_vehicle_attributes,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Проверить косвенный вывод характеристик транспорта без записи в БД."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL PostgreSQL или SQLite; по умолчанию DATABASE_URL.",
    )
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def _raw_name(raw_json: Any) -> str:
    if not isinstance(raw_json, dict):
        return ""
    return str(raw_json.get("name") or "")


def _parameter_name(raw_json: Any) -> str:
    if not isinstance(raw_json, dict):
        return ""
    return str(raw_json.get("itemname") or "")


def _inference_arguments(row) -> dict[str, Any]:
    return {
        "body_type": row.body_type,
        "vehicle_class": row.vehicle_class,
        "seat_count_min": row.seat_count_min,
        "seat_count_max": row.seat_count_max,
        "gross_mass_kg": row.gross_mass_kg,
        "payload_kg_min": row.payload_kg_min,
        "payload_kg_max": row.payload_kg_max,
        "cargo_length_min_mm": row.cargo_length_min_mm,
        "cargo_width_min_mm": row.cargo_width_min_mm,
        "cargo_height_min_mm": row.cargo_height_min_mm,
        "has_permanent_rear_seats": row.has_permanent_rear_seats,
        "has_rear_side_windows": row.has_rear_side_windows,
        "has_rear_windowed_door": row.has_rear_windowed_door,
        "has_separate_cargo_compartment": row.has_separate_cargo_compartment,
        "spec_name": _raw_name(row.raw_json),
        "series_name": _raw_name(row.series_raw_json),
    }


def _record_result(
    counters: dict[str, Counter],
    result: VehicleAttributeInferenceResult,
    *,
    body_type: str | None,
    vehicle_class: str | None,
) -> None:
    for field_name, decision in result.decisions.items():
        value = getattr(decision.value, "value", decision.value)
        label = str(value).lower() if isinstance(value, bool) else str(value)
        counters["value"][(field_name, label)] += 1
        counters["rule"][decision.rule_code] += 1
        counters["confidence"][decision.confidence.value] += 1
    counters["warning"].update(result.warnings)
    special_value = result.value("is_special_purpose")
    special_label = "null" if special_value is None else str(special_value).lower()
    counters["special_purpose"][special_label] += 1
    if body_type in {"VAN", "PICKUP", "TRUCK"}:
        counters["non_passenger_special_purpose"][(body_type, special_label)] += 1
        profile = "".join(
            "1" if result.value(field_name) is True else "0"
            for field_name in (
                "has_permanent_rear_seats",
                "has_rear_side_windows",
                "has_rear_windowed_door",
                "has_separate_cargo_compartment",
            )
        )
        counters["constructive_profile"][(body_type, profile)] += 1
        if special_value is None:
            counters["unresolved_body_class"][
                (
                    body_type,
                    vehicle_class or "NULL",
                )
            ] += 1


def audit_inferences(engine, limit: int | None = None) -> dict[str, Counter]:
    """Прогнать правила для каталога и собрать статистику без записи."""
    counters = {
        "summary": Counter(),
        "value": Counter(),
        "rule": Counter(),
        "confidence": Counter(),
        "warning": Counter(),
        "special_purpose": Counter(),
        "non_passenger_special_purpose": Counter(),
        "unresolved_body_class": Counter(),
        "constructive_profile": Counter(),
    }
    candidate_names = {rule.raw_name for rule in PARAMETER_INFERENCE_RULES}

    with engine.connect() as connection:
        base_statement = (
            select(
                Spec.id,
                Spec.raw_json,
                Series.raw_json.label("series_raw_json"),
                SpecVehicleAttributes.body_type,
                SpecVehicleAttributes.vehicle_class,
                SpecVehicleAttributes.seat_count_min,
                SpecVehicleAttributes.seat_count_max,
                SpecVehicleAttributes.gross_mass_kg,
                SpecVehicleAttributes.payload_kg_min,
                SpecVehicleAttributes.payload_kg_max,
                SpecVehicleAttributes.cargo_length_min_mm,
                SpecVehicleAttributes.cargo_width_min_mm,
                SpecVehicleAttributes.cargo_height_min_mm,
                SpecVehicleAttributes.has_permanent_rear_seats,
                SpecVehicleAttributes.has_rear_side_windows,
                SpecVehicleAttributes.has_rear_windowed_door,
                SpecVehicleAttributes.has_separate_cargo_compartment,
            )
            .outerjoin(Series, Series.id == Spec.series_id)
            .outerjoin(SpecVehicleAttributes, SpecVehicleAttributes.spec_id == Spec.id)
            .order_by(Spec.id)
        )
        if limit is not None:
            base_statement = base_statement.limit(limit)
        base_rows = list(connection.execute(base_statement))
        metadata = {row.id: row for row in base_rows}
        counters["summary"]["specs"] = len(metadata)

        definitions = connection.execute(
            select(ParameterDefinition.id, ParameterDefinition.raw_json)
        )
        parameter_names = {
            row.id: raw_name
            for row in definitions
            if (raw_name := _parameter_name(row.raw_json)) in candidate_names
        }
        counters["summary"]["candidate_definitions"] = len(parameter_names)

        if not metadata:
            return counters

        if parameter_names:
            parameter_statement = (
                select(
                    SpecParameter.spec_id,
                    SpecParameter.parameter_id,
                    SpecParameter.raw_json,
                )
                .where(SpecParameter.parameter_id.in_(parameter_names))
                .order_by(SpecParameter.spec_id, SpecParameter.parameter_id)
            )
            if limit is not None:
                parameter_statement = parameter_statement.where(
                    SpecParameter.spec_id.in_(metadata)
                )
            parameter_rows = connection.execution_options(stream_results=True).execute(
                parameter_statement
            )
        else:
            parameter_rows = ()

        processed: set[int] = set()
        for spec_id, rows in groupby(parameter_rows, key=lambda row: row.spec_id):
            base = metadata.get(spec_id)
            if base is None:
                continue
            parameters = [
                RawParameter(
                    name=parameter_names[row.parameter_id],
                    raw_value=row.raw_json if isinstance(row.raw_json, dict) else {},
                )
                for row in rows
            ]
            result = infer_vehicle_attributes(
                parameters,
                **_inference_arguments(base),
            )
            _record_result(
                counters,
                result,
                body_type=base.body_type,
                vehicle_class=base.vehicle_class,
            )
            processed.add(spec_id)

        for spec_id, base in metadata.items():
            if spec_id in processed:
                continue
            result = infer_vehicle_attributes(
                (),
                **_inference_arguments(base),
            )
            _record_result(
                counters,
                result,
                body_type=base.body_type,
                vehicle_class=base.vehicle_class,
            )

    counters["summary"]["processed"] = len(metadata)
    return counters


def print_counter(title: str, counter: Counter) -> None:
    print(title)
    if not counter:
        print("  нет")
        return
    for key, count in counter.most_common():
        if isinstance(key, tuple):
            label = " = ".join(key)
        else:
            label = key
        print(f"  {label}: {count}")


def main() -> int:
    args = parse_arguments()
    if not args.database_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit должен быть положительным")

    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        counters = audit_inferences(engine, args.limit)
    finally:
        engine.dispose()

    print_counter("Сводка:", counters["summary"])
    print_counter("Выведенные значения:", counters["value"])
    print_counter("Сработавшие правила:", counters["rule"])
    print_counter("Надёжность:", counters["confidence"])
    print_counter("Итог is_special_purpose:", counters["special_purpose"])
    print_counter(
        "Итог для VAN/PICKUP/TRUCK:",
        counters["non_passenger_special_purpose"],
    )
    print_counter(
        "Неразрешённые VAN/PICKUP/TRUCK по кузову и классу:",
        counters["unresolved_body_class"],
    )
    print_counter(
        "Профили конструктивных признаков (сиденья/окна/задняя дверь/грузовой отсек):",
        counters["constructive_profile"],
    )
    print_counter("Предупреждения:", counters["warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
