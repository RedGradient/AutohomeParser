from __future__ import annotations

import argparse
from collections import Counter
from itertools import groupby
import os
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


def _record_result(
    counters: dict[str, Counter],
    result: VehicleAttributeInferenceResult,
) -> None:
    for field_name, decision in result.decisions.items():
        value = getattr(decision.value, "value", decision.value)
        label = str(value).lower() if isinstance(value, bool) else str(value)
        counters["value"][(field_name, label)] += 1
        counters["rule"][decision.rule_code] += 1
        counters["confidence"][decision.confidence.value] += 1
    counters["warning"].update(result.warnings)


def audit_inferences(engine, limit: int | None = None) -> dict[str, Counter]:
    """Прогнать правила для каталога и собрать статистику без записи."""
    counters = {
        "summary": Counter(),
        "value": Counter(),
        "rule": Counter(),
        "confidence": Counter(),
        "warning": Counter(),
    }
    candidate_names = {rule.raw_name for rule in PARAMETER_INFERENCE_RULES}

    with engine.connect() as connection:
        base_statement = (
            select(
                Spec.id,
                Spec.raw_json,
                Series.raw_json.label("series_raw_json"),
                SpecVehicleAttributes.body_type,
            )
            .outerjoin(Series, Series.id == Spec.series_id)
            .outerjoin(SpecVehicleAttributes, SpecVehicleAttributes.spec_id == Spec.id)
            .order_by(Spec.id)
        )
        if limit is not None:
            base_statement = base_statement.limit(limit)
        base_rows = list(connection.execute(base_statement))
        metadata = {
            row.id: (
                row.body_type,
                _raw_name(row.raw_json),
                _raw_name(row.series_raw_json),
            )
            for row in base_rows
        }
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

        if not metadata or not parameter_names:
            return counters

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

        processed: set[int] = set()
        for spec_id, rows in groupby(parameter_rows, key=lambda row: row.spec_id):
            base = metadata.get(spec_id)
            if base is None:
                continue
            body_type, spec_name, series_name = base
            parameters = [
                RawParameter(
                    name=parameter_names[row.parameter_id],
                    raw_value=row.raw_json if isinstance(row.raw_json, dict) else {},
                )
                for row in rows
            ]
            result = infer_vehicle_attributes(
                parameters,
                body_type=body_type,
                spec_name=spec_name,
                series_name=series_name,
            )
            _record_result(counters, result)
            processed.add(spec_id)

        for spec_id, (body_type, spec_name, series_name) in metadata.items():
            if spec_id in processed:
                continue
            result = infer_vehicle_attributes(
                (),
                body_type=body_type,
                spec_name=spec_name,
                series_name=series_name,
            )
            _record_result(counters, result)

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
    print_counter("Предупреждения:", counters["warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
